#ifndef GRAVEBLOOD_PDA_H
#define GRAVEBLOOD_PDA_H

#include <graveblood/input.h>
#include <graveblood/story.h>

typedef enum {
    GB_PDA_MESSAGES = 0,
    GB_PDA_STATUS = 1,
    GB_PDA_FRIENDS = 2,
    GB_PDA_BACKPACK = 3,
} GbPdaPage;

typedef struct {
    u8 active;
    u8 page;
    u8 message_slot;
    u8 friends_cursor;
    u8 friends_scroll;
    u8 return_pending;
} GbPdaRuntime;

typedef struct {
    u8 rerender;
    u8 stop_reserved_audio;
    u8 return_requested;
    s8 sfx_id;
} GbPdaTick;

void gb_pda_reset(GbPdaRuntime* pda);
void gb_pda_open(GbPdaRuntime* pda);
GbPdaTick gb_pda_update(GbPdaRuntime* pda, const GbStoryState* story, const GbInput* input);
s8 gb_pda_message_stream(const GbPdaRuntime* pda, const GbStoryState* story);
u8 gb_pda_friend_index(const GbPdaRuntime* pda, u8 row);

#endif
