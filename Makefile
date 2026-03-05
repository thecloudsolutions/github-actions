# Download makefile
$(shell mkdir -p .makefiles && curl -sSL -o .makefiles/Makefile.repository https://raw.githubusercontent.com/thecloudsolutions/makefiles/refs/heads/main/Makefile.repository)

# Include explicitly
include .makefiles/Makefile.repository
