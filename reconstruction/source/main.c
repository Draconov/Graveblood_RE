#if defined(GB_EMULATOR_SELFTEST) || defined(GB_DEVICE_SELFTEST)
#include <graveblood/emulator_selftest.h>
#else
#include <graveblood/game.h>
#endif

int main(void)
{
#ifdef GB_EMULATOR_SELFTEST
    gb_emulator_selftest_run();
#elif defined(GB_DEVICE_SELFTEST)
    gb_device_selftest_run();
#else
    gb_game_run();
#endif
    return 0;
}
