#ifndef GRAVEBLOOD_AUDIO_H
#define GRAVEBLOOD_AUDIO_H

#include <gba.h>
#include <graveblood/assets.h>

enum {
    GB_AUDIO_CHANNEL_COUNT = 8,
    GB_AUDIO_SAMPLE_RATE = 16384,
    GB_AUDIO_BUFFER_SAMPLES = 256,
    GB_AUDIO_DEFAULT_SFX_VOLUME = 0x50,
    GB_AUDIO_DEFAULT_MUSIC_VOLUME = 0x90,
    GB_AUDIO_MASTER_SCALE = 0x180,
};

void gb_audio_init(void);
void gb_audio_shutdown(void);
int gb_audio_play_sfx(u8 sound_id);
int gb_audio_play_sfx_volume(u8 sound_id, u16 volume);
int gb_audio_play_music(u8 sound_id);
void gb_audio_stop_music(void);
void gb_audio_stop_channel(u8 channel);
void gb_audio_set_channel_volume(u8 channel, u16 volume);

#if defined(GB_EMULATOR_SELFTEST) || defined(GB_DEVICE_SELFTEST)
extern volatile u32 gb_audio_selftest_irq_count;
#endif

#ifdef GB_AUDIO_TESTING
void gb_audio_mix_block(s8* destination, u16 sample_count);
#endif

#endif
