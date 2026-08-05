# greet -- build and package the release bundle.
#
#   make            build everything and package dist/greet-$(VERSION).tar.gz
#   make check      run the binary once as a smoke test
#   make clean      remove build/, stage/ and dist/

VERSION  := $(shell cat VERSION)
PREFIX   := greet-$(VERSION)

CC       ?= cc
CFLAGS   := -O2 -g -Wall -Wextra -Isrc

BUILD    := build
STAGE    := stage
DIST     := dist
LIBOBJS  := $(BUILD)/greet.o $(BUILD)/util.o

.PHONY: all check clean
all: $(DIST)/$(PREFIX).tar.gz

src/buildinfo.h: tools/gen-buildinfo.sh VERSION
	sh tools/gen-buildinfo.sh > $@

$(BUILD)/%.o: src/%.c src/greet.h src/buildinfo.h
	mkdir -p $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/libgreet.a: $(LIBOBJS)
	ar rcs $@ $(LIBOBJS)

$(BUILD)/greet: src/main.c src/greet.h src/buildinfo.h $(BUILD)/libgreet.a
	$(CC) $(CFLAGS) src/main.c $(BUILD)/libgreet.a -o $@

# Lay the bundle out the way it installs: bin, lib, include, share.
$(STAGE)/$(PREFIX): $(BUILD)/greet $(BUILD)/libgreet.a
	rm -rf $@
	mkdir -p $@/bin $@/lib $@/include $@/share/docs
	cp $(BUILD)/greet $@/bin/greet
	cp $(BUILD)/libgreet.a $@/lib/libgreet.a
	cp src/greet.h $@/include/greet.h
	cp docs/* $@/share/docs/
	cp VERSION CHANGELOG.md $@/
	sh tools/gen-manifest.sh $@ > $@/share/manifest.txt

$(DIST)/$(PREFIX).tar.gz: $(STAGE)/$(PREFIX)
	mkdir -p $(DIST)
	rm -f $(DIST)/$(PREFIX).tar $(DIST)/$(PREFIX).tar.gz
	cd $(STAGE) && find $(PREFIX) | sort | \
		tar cf ../$(DIST)/$(PREFIX).tar --no-recursion -T -
	gzip -9 $(DIST)/$(PREFIX).tar

check: $(BUILD)/greet
	./$(BUILD)/greet --version
	./$(BUILD)/greet Ada
	./$(BUILD)/greet --upper Ada

clean:
	rm -rf $(BUILD) $(STAGE) $(DIST) src/buildinfo.h
