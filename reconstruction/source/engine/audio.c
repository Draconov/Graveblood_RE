#include <graveblood/audio.h>

#include <stddef.h>

#ifndef GB_AUDIO_TESTING
#define GB_REG16(address) (*(volatile u16*)(address))
#define GB_REG32(address) (*(volatile u32*)(address))

#define GB_REG_SOUNDCNT_H 0x04000082u
#define GB_REG_SOUNDCNT_X 0x04000084u
#define GB_REG_FIFO_A     0x040000A0u
#define GB_REG_DMA1SAD    0x040000BCu
#define GB_REG_DMA1DAD    0x040000C0u
#define GB_REG_DMA1CNT_H  0x040000C6u
#define GB_REG_TM0D       0x04000100u
#define GB_REG_TM0CNT     0x04000102u
#define GB_REG_TM1D       0x04000104u
#define GB_REG_TM1CNT     0x04000106u

static s8 gb_audio_buffers[2][GB_AUDIO_BUFFER_SAMPLES] __attribute__((aligned(4)));
static u8 gb_audio_dma_buffer;
#endif


typedef struct {
    u8 mode;
    u8 reserved;
    u16 _padding;
    u32 volume;
    const s8* start;
    const s8* end;
    const s8* cursor;
} GbAudioChannel;

static GbAudioChannel gb_audio_channels[GB_AUDIO_CHANNEL_COUNT];
static int gb_audio_music_channel = -1;

void gb_audio_mix_block(s8* destination, u16 sample_count);

#ifndef GB_AUDIO_TESTING
static void gb_audio_dma_start(u8 buffer_index)
{
    GB_REG16(GB_REG_DMA1CNT_H) = 0;
    GB_REG32(GB_REG_DMA1SAD) = (u32)(unsigned long)&gb_audio_buffers[buffer_index][0];
    GB_REG32(GB_REG_DMA1DAD) = GB_REG_FIFO_A;
    GB_REG16(GB_REG_DMA1CNT_H) = 0xB200;
}

static void gb_audio_timer1_irq(void)
{
    const u8 consumed = gb_audio_dma_buffer;
    const u8 next = (u8)(consumed ^ 1u);

    gb_audio_dma_start(next);
    gb_audio_dma_buffer = next;
    gb_audio_mix_block(gb_audio_buffers[consumed], GB_AUDIO_BUFFER_SAMPLES);
}

static void gb_audio_hardware_start(void)
{
    gb_audio_mix_block(gb_audio_buffers[0], GB_AUDIO_BUFFER_SAMPLES);
    gb_audio_mix_block(gb_audio_buffers[1], GB_AUDIO_BUFFER_SAMPLES);
    gb_audio_dma_buffer = 0;

    GB_REG16(GB_REG_SOUNDCNT_X) = 0x0080;
    GB_REG16(GB_REG_SOUNDCNT_H) = 0x0B04;

    irqInit();
    irqSet(IRQ_TIMER1, gb_audio_timer1_irq);
    irqEnable(IRQ_TIMER1);

    GB_REG16(GB_REG_TM0CNT) = 0;
    GB_REG16(GB_REG_TM1CNT) = 0;
    GB_REG16(GB_REG_TM0D) = 0xFC00;
    GB_REG16(GB_REG_TM1D) = 0xFF00;

    gb_audio_dma_start(0);

    GB_REG16(GB_REG_TM0CNT) = 0x0080;
    GB_REG16(GB_REG_TM1CNT) = 0x00C4;
}

static void gb_audio_hardware_stop(void)
{
    GB_REG16(GB_REG_TM1CNT) = 0;
    GB_REG16(GB_REG_TM0CNT) = 0;
    GB_REG16(GB_REG_DMA1CNT_H) = 0;
    irqDisable(IRQ_TIMER1);
    GB_REG16(GB_REG_SOUNDCNT_H) = 0;
    GB_REG16(GB_REG_SOUNDCNT_X) = 0;
}
#endif

static s32 gb_audio_asr8(s32 value)
{
    if(value >= 0) {
        return value / 256;
    }
    return -(((-value) + 255) / 256);
}

static s16 gb_audio_wrap_s16(s32 value)
{
    const u16 bits = (u16)((u32)value & 0xffffu);
    return bits < 0x8000u ? (s16)bits : (s16)((s32)bits - 0x10000);
}

static s8 gb_audio_low_s8(s32 value)
{
    const u8 bits = (u8)((u32)value & 0xffu);
    return bits < 0x80u ? (s8)bits : (s8)((s32)bits - 0x100);
}

static void gb_audio_clear_channel(int channel)
{
    GbAudioChannel* state = &gb_audio_channels[channel];
    state->mode = 0;
    state->reserved = 0;
    state->volume = 0;
    state->start = NULL;
    state->end = NULL;
    state->cursor = NULL;
}

static int gb_audio_first_free_channel(void)
{
    for(int channel = 0; channel < GB_AUDIO_CHANNEL_COUNT; ++channel) {
        if(gb_audio_channels[channel].reserved == 0 && gb_audio_channels[channel].mode == 0) {
            return channel;
        }
    }
    return -1;
}

static int gb_audio_start_sample(u8 sound_id, u8 required_role, u8 mode, u16 volume, u8 reserved)
{
    if(sound_id >= GB_AUDIO_SAMPLE_COUNT) {
        return -1;
    }

    const GbAudioSample* sample = &gb_audio_samples[sound_id];
    if(sample->role != required_role) {
        return -1;
    }

    const u32 aligned_length = sample->byte_length & ~3u;
    if(sample->data == NULL || aligned_length == 0) {
        return -1;
    }

    const int channel = gb_audio_first_free_channel();
    if(channel < 0) {
        return -1;
    }

    GbAudioChannel* state = &gb_audio_channels[channel];
    state->mode = mode;
    state->reserved = reserved;
    state->volume = volume;
    state->start = sample->data;
    state->end = sample->data + aligned_length;
    state->cursor = sample->data;
    return channel;
}

void gb_audio_init(void)
{
    for(int channel = 0; channel < GB_AUDIO_CHANNEL_COUNT; ++channel) {
        gb_audio_clear_channel(channel);
    }
    gb_audio_music_channel = -1;
#ifndef GB_AUDIO_TESTING
    gb_audio_hardware_start();
#endif
}

void gb_audio_shutdown(void)
{
#ifndef GB_AUDIO_TESTING
    gb_audio_hardware_stop();
#endif
    for(int channel = 0; channel < GB_AUDIO_CHANNEL_COUNT; ++channel) {
        gb_audio_clear_channel(channel);
    }
    gb_audio_music_channel = -1;
}

int gb_audio_play_sfx(u8 sound_id)
{
    return gb_audio_start_sample(
        sound_id,
        GB_AUDIO_ROLE_SFX,
        1,
        GB_AUDIO_DEFAULT_SFX_VOLUME,
        0);
}

int gb_audio_play_music(u8 sound_id)
{
    if(sound_id >= GB_AUDIO_SAMPLE_COUNT || gb_audio_samples[sound_id].role != GB_AUDIO_ROLE_MUSIC) {
        return -1;
    }

    gb_audio_stop_music();
    const int channel = gb_audio_start_sample(
        sound_id,
        GB_AUDIO_ROLE_MUSIC,
        2,
        GB_AUDIO_DEFAULT_MUSIC_VOLUME,
        1);
    if(channel >= 0) {
        gb_audio_music_channel = channel;
    }
    return channel;
}

void gb_audio_stop_music(void)
{
    if(gb_audio_music_channel >= 0 && gb_audio_music_channel < GB_AUDIO_CHANNEL_COUNT) {
        gb_audio_clear_channel(gb_audio_music_channel);
    }
    gb_audio_music_channel = -1;
}

void gb_audio_stop_channel(u8 channel)
{
    if(channel >= GB_AUDIO_CHANNEL_COUNT) {
        return;
    }
    if((int)channel == gb_audio_music_channel) {
        gb_audio_music_channel = -1;
    }
    gb_audio_clear_channel(channel);
}

void gb_audio_set_channel_volume(u8 channel, u16 volume)
{
    if(channel >= GB_AUDIO_CHANNEL_COUNT) {
        return;
    }
    gb_audio_channels[channel].volume = volume;
}

void gb_audio_mix_block(s8* destination, u16 sample_count)
{
    s16 mix[GB_AUDIO_BUFFER_SAMPLES];
    if(destination == NULL || sample_count > GB_AUDIO_BUFFER_SAMPLES) {
        return;
    }

    for(u16 index = 0; index < sample_count; ++index) {
        mix[index] = 0;
    }

    for(int channel = 0; channel < GB_AUDIO_CHANNEL_COUNT; ++channel) {
        GbAudioChannel* state = &gb_audio_channels[channel];
        if(state->mode == 0) {
            continue;
        }

        for(u16 index = 0; index < sample_count; ++index) {
            if(state->cursor >= state->end) {
                if(state->mode == 1) {
                    gb_audio_clear_channel(channel);
                    break;
                }
                state->cursor = state->start;
            }

            const s32 contribution = gb_audio_asr8((s32)(*state->cursor++) * (s32)state->volume);
            mix[index] = gb_audio_wrap_s16((s32)mix[index] + contribution);
        }
    }

    for(u16 index = 0; index < sample_count; ++index) {
        const s32 scaled = gb_audio_asr8((s32)mix[index] * GB_AUDIO_MASTER_SCALE);
        destination[index] = gb_audio_low_s8(scaled);
    }
}
