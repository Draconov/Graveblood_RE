.SUFFIXES:

ifeq ($(strip $(DEVKITARM)),)
$(error "Please set DEVKITARM in your environment. export DEVKITARM=<path to>devkitARM")
endif

include $(DEVKITARM)/gba_rules

export PATH := $(DEVKITARM)/bin:$(PATH)

TARGET := Graveblood_RE
BUILD := build
SOURCES := source source/engine source/game data
INCLUDES := include
DATA :=
GRAPHICS :=

ARCH := -mthumb -mthumb-interwork
CFLAGS := -g -O2 -Wall -Wextra -std=gnu11 -mcpu=arm7tdmi -mtune=arm7tdmi -fomit-frame-pointer $(ARCH)
CFLAGS += $(INCLUDE)
ASFLAGS := -g $(ARCH)
LDFLAGS := -g $(ARCH) -Wl,-Map,$(notdir $*.map)

LIBS := -lgba
LIBDIRS := $(LIBGBA)

GAME_TITLE := GRAVEBLOODRE
GAME_CODE := GBR0
MAKER_CODE := 00

ifneq ($(BUILD),$(notdir $(CURDIR)))

export OUTPUT := $(CURDIR)/$(TARGET)
export VPATH := $(foreach dir,$(SOURCES),$(CURDIR)/$(dir))
export DEPSDIR := $(CURDIR)/$(BUILD)

CFILES := $(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.c)))
SFILES := $(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.s)))

export LD := $(CC)
export OFILES := $(CFILES:.c=.o) $(SFILES:.s=.o)
export INCLUDE := $(foreach dir,$(INCLUDES),-iquote $(CURDIR)/$(dir)) \
                  $(foreach dir,$(LIBDIRS),-I$(dir)/include) \
                  -I$(CURDIR)/$(BUILD)
export LIBPATHS := $(foreach dir,$(LIBDIRS),-L$(dir)/lib)

.PHONY: $(BUILD) clean

$(BUILD):
	@[ -d $@ ] || mkdir -p $@
	@$(MAKE) --no-print-directory -C $(BUILD) -f $(CURDIR)/Makefile

clean:
	@echo clean ...
	@rm -fr $(BUILD) $(TARGET).elf $(TARGET).gba $(TARGET).map

else

DEPENDS := $(OFILES:.o=.d)

$(OUTPUT).gba : $(OUTPUT).elf
$(OUTPUT).elf : $(OFILES)

-include $(DEPENDS)

endif
