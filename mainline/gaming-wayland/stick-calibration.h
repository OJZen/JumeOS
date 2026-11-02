#pragma once
#include <algorithm>
#include <array>
#include <cstdint>

namespace Stick {
constexpr int32_t Full = 32767, MinimumTravel = 8192;
struct Axis {
    int32_t minimum = -Full, center = 0, maximum = Full;
    bool valid() const {
        return minimum >= -Full && maximum <= Full && center >= -MinimumTravel && center <= MinimumTravel
            && minimum < center && maximum > center
            && center - minimum >= MinimumTravel && maximum - center >= MinimumTravel;
    }
    int32_t apply(int32_t value) const {
        if (!valid()) return value;
        const int64_t delta = int64_t(value) - center;
        const int64_t span = delta < 0 ? center - minimum : maximum - center;
        return int32_t(std::clamp(delta * Full / span, int64_t(-Full), int64_t(Full)));
    }
};
using Profile = std::array<Axis, 4>;
inline bool valid(const Profile &profile) {
    return std::all_of(profile.begin(), profile.end(), [](const Axis &axis) { return axis.valid(); });
}
inline int32_t normalized(int32_t value, int32_t minimum, int32_t maximum) {
    const int64_t center = (int64_t(minimum) + maximum) / 2, delta = int64_t(value) - center;
    const int64_t span = std::max<int64_t>(1, delta < 0 ? center - minimum : int64_t(maximum) - center);
    return int32_t(std::clamp(delta * Full / span, int64_t(-Full), int64_t(Full)));
}
inline int32_t native(int32_t value, int32_t minimum, int32_t maximum) {
    const int64_t center = (int64_t(minimum) + maximum) / 2;
    const int64_t span = value < 0 ? center - minimum : int64_t(maximum) - center;
    return int32_t(center + int64_t(value) * span / Full);
}
}
