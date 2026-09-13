// Qt defines emit as an empty macro; the shared packet/policy header must survive it.
#define emit
#include "input-route.h"
#undef emit
#include <cassert>
#include <cstdio>
#include <vector>
using namespace Route;

int main() {
    for (const auto first : {L3, R3}) {
        Policy policy(120); Sample sample; std::vector<Sample> emitted; int panels = 0;
        auto tick = [&](uint32_t keys, int64_t time) {
            sample.keys = keys;
            policy.update(sample, keys == 0, time, [&](const Sample &value) { emitted.push_back(value); }, [&] { ++panels; });
        };
        tick(first, 0); assert(emitted.empty()); // Startup held controls are not delivered.
        tick(0, 1); emitted.clear();
        tick(first, 10); tick(first, 129);
        for (auto value : emitted) assert(!(value.keys & Chord));
        tick(Chord, 130); assert(panels == 1 && policy.ownerPending);
        tick(Chord, 131); tick(0, 140); assert(panels == 1);
        policy.setMode(Game); tick(first, 141); assert(policy.waiting);
        tick(0, 142); emitted.clear();
        tick(first, 150); tick(0, 160);
        assert(emitted.size() == 3 && emitted[1].keys == first && emitted[2].keys == 0);
        emitted.clear(); tick(first, 200); tick(first, 320); tick(Chord, 330);
        assert(emitted.back().keys == Chord && panels == 1); // Late overlap keeps normal clicks.
        tick(0, 340); tick(Chord, 350); assert(panels == 2);
        policy.setMode(Ui); tick(0, 360); emitted.clear();
        tick(1U << 4 | 1U << 5, 370); assert(emitted.back().keys == (1U << 4 | 1U << 5));
    }
    std::puts("INPUT_POLICY_PASS: both chord orders, boundary time, no repeat, short clicks, delayed overlap, neutral ownership and shoulder passthrough");
}
