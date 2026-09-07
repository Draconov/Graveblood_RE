# Graveblood_RE clean-room reconstruction build.
#
# LIBBUTANO is intentionally overridable so local development and CI can use
# the same project with a pinned external Butano checkout.

TARGET          := Graveblood_RE
BUILD           := build
LIBBUTANO       ?= ../vendor/butano/butano
PYTHON          ?= python
SOURCES         := src
INCLUDES        :=
DATA            :=
GRAPHICS        :=
AUDIO           :=
AUDIOBACKEND    := null
AUDIOTOOL       :=
DMGAUDIO        :=
DMGAUDIOBACKEND := null
ROMTITLE        := GRAVEBLOOD
ROMCODE         := GBR0
USERFLAGS       :=
USERCXXFLAGS    :=
USERASFLAGS     :=
USERLDFLAGS     :=
USERLIBDIRS     :=
USERLIBS        :=
DEFAULTLIBS     :=
STACKTRACE      :=
USERBUILD       :=
EXTTOOL         :=

ifndef LIBBUTANOABS
export LIBBUTANOABS := $(realpath $(LIBBUTANO))
endif

ifeq ($(LIBBUTANOABS),)
$(error Butano not found. Set LIBBUTANO to the Butano library directory, for example ../vendor/butano/butano)
endif

include $(LIBBUTANOABS)/butano.mak
