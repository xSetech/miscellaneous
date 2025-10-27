/*
 * test_byteswap.c - Test program for byteswap.h compatibility header
 *
 * Compile on macOS with: gcc -o test_byteswap test_byteswap.c
 * Compile on Linux with: gcc -o test_byteswap test_byteswap.c
 */

#include <stdio.h>
#include <stdint.h>
#include "byteswap.h"

int main(void) {
    uint16_t val16 = 0x1234;
    uint32_t val32 = 0x12345678;
    uint64_t val64 = 0x123456789ABCDEF0ULL;

    printf("Byte swap test:\n\n");

    printf("16-bit: 0x%04x -> 0x%04x\n", val16, bswap_16(val16));
    printf("32-bit: 0x%08x -> 0x%08x\n", val32, bswap_32(val32));
    printf("64-bit: 0x%016llx -> 0x%016llx\n",
           (unsigned long long)val64,
           (unsigned long long)bswap_64(val64));

    /* Verify correctness */
    int passed = 1;
    if (bswap_16(0x1234) != 0x3412) passed = 0;
    if (bswap_32(0x12345678) != 0x78563412) passed = 0;
    if (bswap_64(0x123456789ABCDEF0ULL) != 0xF0DEBC9A78563412ULL) passed = 0;

    printf("\nTest %s!\n", passed ? "PASSED" : "FAILED");

    return passed ? 0 : 1;
}
