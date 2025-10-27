/*
 * byteswap.h - Compatibility shim for macOS
 *
 * This header provides GNU-style byteswap functions on macOS by mapping
 * them to the native OSByteOrder.h functions.
 *
 * On Linux/GNU systems, byteswap.h provides:
 *   - bswap_16(x) - swap bytes in a 16-bit value
 *   - bswap_32(x) - swap bytes in a 32-bit value
 *   - bswap_64(x) - swap bytes in a 64-bit value
 *
 * This shim maps these to macOS equivalents from <libkern/OSByteOrder.h>
 */

#ifndef _BYTESWAP_H
#define _BYTESWAP_H

#ifdef __APPLE__

#include <libkern/OSByteOrder.h>

/* Map GNU byteswap functions to macOS OSByteOrder functions */
#define bswap_16(x) OSSwapInt16(x)
#define bswap_32(x) OSSwapInt32(x)
#define bswap_64(x) OSSwapInt64(x)

#else

/* On non-Apple systems, include the standard header if available */
#if __has_include(<byteswap.h>)
#include_next <byteswap.h>
#else
/* Fallback implementations using compiler builtins */
#if defined(__GNUC__) || defined(__clang__)
#define bswap_16(x) __builtin_bswap16(x)
#define bswap_32(x) __builtin_bswap32(x)
#define bswap_64(x) __builtin_bswap64(x)
#else
/* Manual implementations as last resort */
#include <stdint.h>

static inline uint16_t bswap_16(uint16_t x) {
    return (x >> 8) | (x << 8);
}

static inline uint32_t bswap_32(uint32_t x) {
    return ((x & 0xff000000u) >> 24) |
           ((x & 0x00ff0000u) >>  8) |
           ((x & 0x0000ff00u) <<  8) |
           ((x & 0x000000ffu) << 24);
}

static inline uint64_t bswap_64(uint64_t x) {
    return ((x & 0xff00000000000000ull) >> 56) |
           ((x & 0x00ff000000000000ull) >> 40) |
           ((x & 0x0000ff0000000000ull) >> 24) |
           ((x & 0x000000ff00000000ull) >>  8) |
           ((x & 0x00000000ff000000ull) <<  8) |
           ((x & 0x0000000000ff0000ull) << 24) |
           ((x & 0x000000000000ff00ull) << 40) |
           ((x & 0x00000000000000ffull) << 56);
}

#endif /* __GNUC__ || __clang__ */
#endif /* __has_include */
#endif /* __APPLE__ */

#endif /* _BYTESWAP_H */
