#ifndef ZEROSIS_CV_CHECKED_NARROW_H
#define ZEROSIS_CV_CHECKED_NARROW_H

#include <cstddef>
#include <cstdint>
#include <limits>
#include <new>
#include <stdexcept>
#include <type_traits>

// Native addresses/byte sizes may grow; existing game counts and save fields do not.
namespace CvChecked
{
namespace Detail
{
template<class To> inline bool NegativeFits(std::intmax_t value, std::true_type)
{
    return value >= static_cast<std::intmax_t>((std::numeric_limits<To>::min)());
}
template<class To> inline bool NegativeFits(std::intmax_t, std::false_type) { return false; }
template<class To> inline bool PositiveFits(std::uintmax_t value)
{
    return value <= static_cast<std::uintmax_t>((std::numeric_limits<To>::max)());
}
template<class To, class From> inline bool Fits(From value, std::true_type)
{
    const std::intmax_t number = static_cast<std::intmax_t>(value);
    return number < 0 ? NegativeFits<To>(number, std::is_signed<To>())
                      : PositiveFits<To>(static_cast<std::uintmax_t>(number));
}
template<class To, class From> inline bool Fits(From value, std::false_type)
{
    return PositiveFits<To>(static_cast<std::uintmax_t>(value));
}
}

template<class To, class From> inline bool TryInteger(From value, To& result) noexcept
{
    static_assert(std::is_integral<To>::value && std::is_integral<From>::value,
                  "Integer conversions require integral types, not pointers/enums/floats");
    if (!Detail::Fits<To>(value, std::is_signed<From>())) return false;
    result = static_cast<To>(value);
    return true;
}

template<class To, class From> inline To Integer(From value)
{
    To result = 0;
    if (!TryInteger(value, result)) throw std::range_error("Game integer range exceeded");
    return result;
}

inline std::size_t AddBytes(std::size_t left, std::size_t right)
{
    if (right > (std::numeric_limits<std::size_t>::max)() - left)
        throw std::bad_array_new_length();
    return left + right;
}
inline std::size_t MultiplyBytes(std::size_t left, std::size_t right)
{
    if (left && right > (std::numeric_limits<std::size_t>::max)() / left)
        throw std::bad_array_new_length();
    return left * right;
}

inline std::size_t Array2DBytes(std::size_t rows, std::size_t columns,
                               std::size_t elementBytes, std::size_t pointerBytes)
{
    return AddBytes(MultiplyBytes(rows, pointerBytes),
                    MultiplyBytes(MultiplyBytes(rows, columns), elementBytes));
}

inline int CountProduct(int multiplier, std::size_t count)
{
    // Widen *before* multiplication, preserving negative effects as well as positive ones.
    return Integer<int>(static_cast<std::int64_t>(multiplier) * Integer<int>(count));
}
}
#endif
