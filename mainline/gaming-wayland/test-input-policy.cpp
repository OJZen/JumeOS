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
            policy.update(sample, keys == 0, time, [&](const Sample &value) { emitted.push_back(value); }, [&](uint32_t action) { assert(action==Panel);++panels; });
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
    for(auto button:{X,Y,Start}) {
        Policy policy(120);Sample sample;std::vector<Sample> output;std::vector<uint32_t> actions;
        auto tick=[&](uint32_t keys,int64_t now){sample.keys=keys;policy.update(sample,!keys,now,[&](const Sample &s){output.push_back(s);},[&](uint32_t action){actions.push_back(action);});};
        tick(0,0);tick(Select,10);tick(Select|button,20);
        if(button==Start){assert(actions.empty());tick(Select|Start,2019);assert(actions.empty());tick(Select|Start,2020);}
        assert(actions.size()==1&&actions[0]==(button==X?Close:button==Y?Tasks:Kill));
        tick(Select|button,3000);tick(0,3010);assert(actions.size()==1);
        for(const auto &s:output)assert(!(s.keys&(Select|button)));
        policy.setMode(Game);tick(0,4000);actions.clear();output.clear();
        tick(Select|Start,4010);tick(0,4050);assert(actions.size()==1&&actions[0]==Home);
        policy.setMode(Ui);tick(0,5000);actions.clear();output.clear();tick(Select,5010);tick(0,5020);
        assert(actions.empty()&&output[output.size()-2].keys==Select&&output.back().keys==0);
    }
    std::puts("INPUT_POLICY_PASS: chords, short-home/long-kill, modifier suppression and neutral ownership");
}
