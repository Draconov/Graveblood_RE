#include <graveblood/pda.h>

#define GB_PDA_PAGE_COUNT_LOCAL 4
#define GB_PDA_MESSAGE_SLOT_COUNT 4
#define GB_PDA_FRIEND_COUNT_LOCAL 6
#define GB_PDA_FRIEND_VISIBLE_ROWS_LOCAL 3

static GbPdaTick gb_pda_tick_none(void) {
    GbPdaTick tick;
    tick.rerender = 0;
    tick.stop_reserved_audio = 0;
    tick.return_requested = 0;
    tick.sfx_id = -1;
    return tick;
}

static s8 gb_pda_stream_for_slot(const GbStoryState* story, u8 slot) {
    if(slot == 0) {
        return story->primary_message_stream;
    }
    if(slot < GB_PDA_MESSAGE_SLOT_COUNT) {
        return story->auxiliary_message_streams[slot - 1];
    }
    return -1;
}

void gb_pda_reset(GbPdaRuntime* pda) {
    pda->active = 0;
    pda->page = GB_PDA_MESSAGES;
    pda->message_slot = 0;
    pda->friends_cursor = 0;
    pda->friends_scroll = 0;
    pda->return_pending = 0;
}

void gb_pda_open(GbPdaRuntime* pda) {
    pda->active = 1;
    pda->page = GB_PDA_MESSAGES;
    /* The original open path does not clear the message selector at +0x18. */
    pda->friends_cursor = 0;
    pda->friends_scroll = 0;
    pda->return_pending = 0;
}

s8 gb_pda_message_stream(const GbPdaRuntime* pda, const GbStoryState* story) {
    return gb_pda_stream_for_slot(story, pda->message_slot);
}

u8 gb_pda_friend_index(const GbPdaRuntime* pda, u8 row) {
    u8 index = (u8)(pda->friends_scroll + row);
    if(row >= GB_PDA_FRIEND_VISIBLE_ROWS_LOCAL || index >= GB_PDA_FRIEND_COUNT_LOCAL) {
        return 0xFF;
    }
    return index;
}

GbPdaTick gb_pda_update(GbPdaRuntime* pda, const GbStoryState* story, const GbInput* input) {
    GbPdaTick tick = gb_pda_tick_none();

    if(!pda->active) {
        return tick;
    }

    /* Original Player_update consumes the return-pending byte before START. */
    if(pda->return_pending) {
        pda->return_pending = 0;
        pda->active = 0;
        tick.return_requested = 1;
        tick.sfx_id = 7;
        return tick;
    }

    if(input->pressed & KEY_START) {
        gb_pda_open(pda);
        tick.rerender = 1;
        tick.stop_reserved_audio = 1;
        tick.sfx_id = 6;
        return tick;
    }

    if(input->pressed & KEY_R) {
        if(pda->page + 1 < GB_PDA_PAGE_COUNT_LOCAL) {
            ++pda->page;
            tick.rerender = 1;
            tick.sfx_id = 11;
        }
        return tick;
    }

    if(input->pressed & KEY_L) {
        if(pda->page > GB_PDA_MESSAGES) {
            --pda->page;
            tick.rerender = 1;
            tick.sfx_id = 11;
        }
        return tick;
    }

    if(pda->page == GB_PDA_MESSAGES) {
        if(input->pressed & KEY_RIGHT) {
            if(pda->message_slot + 1 < GB_PDA_MESSAGE_SLOT_COUNT) {
                u8 candidate = (u8)(pda->message_slot + 1);
                if(gb_pda_stream_for_slot(story, candidate) >= 0) {
                    pda->message_slot = candidate;
                    tick.rerender = 1;
                    tick.sfx_id = 4;
                }
            }
            return tick;
        }
        if(input->pressed & KEY_LEFT) {
            if(pda->message_slot > 0) {
                u8 candidate = (u8)(pda->message_slot - 1);
                if(gb_pda_stream_for_slot(story, candidate) >= 0) {
                    pda->message_slot = candidate;
                    tick.rerender = 1;
                    tick.sfx_id = 4;
                }
            }
            return tick;
        }
    }

    if(pda->page == GB_PDA_FRIENDS) {
        if(input->pressed & KEY_UP) {
            if(pda->friends_cursor > 0) {
                --pda->friends_cursor;
                tick.rerender = 1;
                tick.sfx_id = 4;
            } else if(pda->friends_scroll > 0) {
                --pda->friends_scroll;
                tick.rerender = 1;
                tick.sfx_id = 4;
            } else {
                tick.sfx_id = 12;
            }
            return tick;
        }
        if(input->pressed & KEY_DOWN) {
            if(pda->friends_cursor + 1 < GB_PDA_FRIEND_VISIBLE_ROWS_LOCAL &&
               pda->friends_scroll + pda->friends_cursor + 1 < GB_PDA_FRIEND_COUNT_LOCAL) {
                ++pda->friends_cursor;
                tick.rerender = 1;
                tick.sfx_id = 4;
            } else if(pda->friends_scroll + GB_PDA_FRIEND_VISIBLE_ROWS_LOCAL < GB_PDA_FRIEND_COUNT_LOCAL) {
                ++pda->friends_scroll;
                tick.rerender = 1;
                tick.sfx_id = 4;
            } else {
                tick.sfx_id = 12;
            }
            return tick;
        }
    }

    return tick;
}
