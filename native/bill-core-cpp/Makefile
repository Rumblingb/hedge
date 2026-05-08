CXX ?= clang++
CXXFLAGS ?= -std=c++20 -O2 -Wall -Wextra -Wpedantic
OUT_DIR ?= ../../.rumbling-hedge/native
BIN := $(OUT_DIR)/bill-core

.PHONY: all clean smoke

all: $(BIN)

$(BIN): src/main.cpp
	mkdir -p $(OUT_DIR)
	$(CXX) $(CXXFLAGS) $< -o $@

smoke: $(BIN)
	$(BIN) gate --mode paper --net-edge-pct 1.25 --stake 1 --kill-switch false --live-readiness false

clean:
	rm -f $(BIN)
