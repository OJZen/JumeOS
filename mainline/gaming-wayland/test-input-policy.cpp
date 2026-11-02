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
    // Select shortcuts (§7.2): Y = Tasks, Start short = Home, Start 2 s = Kill; never seen by the owner.
    for(auto button:{Y,Start}) {
        Policy policy(80);Sample sample;std::vector<Sample> output;std::vector<uint32_t> actions;
        auto tick=[&](uint32_t keys,int64_t now){sample.keys=keys;policy.update(sample,!keys,now,[&](const Sample &s){output.push_back(s);},[&](uint32_t action){actions.push_back(action);});};
        tick(0,0);tick(Select,10);tick(Select|button,20);
        if(button==Start){assert(actions.empty());tick(Select|Start,2019);assert(actions.empty());tick(Select|Start,2020);}
        assert(actions.size()==1&&actions[0]==(button==Y?Tasks:Kill));
        tick(Select|button,3000);tick(0,3010);assert(actions.size()==1);
        for(const auto &s:output)assert(!(s.keys&(Select|button)));
        policy.setMode(Game);tick(0,4000);actions.clear();output.clear();
        tick(Select|Start,4010);tick(0,4050);assert(actions.size()==1&&actions[0]==Home);
        policy.setMode(Ui);tick(0,5000);actions.clear();output.clear();tick(Select,5010);tick(0,5020);
        assert(actions.empty()&&output[output.size()-2].keys==Select&&output.back().keys==0);
    }
    {
        Policy policy(80);Sample sample;std::vector<Sample> output;std::vector<uint32_t> actions;
        auto tick=[&](uint32_t keys,int64_t now){sample.keys=keys;policy.update(sample,!keys,now,[&](const Sample &s){output.push_back(s);},[&](uint32_t action){actions.push_back(action);});};
        auto delivered=[&](uint32_t keys){for(const auto &s:output)if(s.keys==keys)return true;return false;};
        constexpr uint32_t A=1U<<1;
        // Desktop: Select with another key does nothing, and its release opens nothing.
        tick(0,0);tick(Select,10);tick(Select|A,20);tick(Select,30);tick(0,40);
        assert(actions.empty());for(const auto &s:output)assert(!s.keys);
        // Game: Select + X is no longer a shortcut; Select goes first, then X (emulator hotkeys).
        policy.setMode(Game);tick(0,100);output.clear();
        tick(Select,110);assert(!delivered(Select));
        tick(Select|X,120);assert(actions.empty()&&output.size()>=2);
        assert(output[output.size()-2].keys==Select&&output.back().keys==(Select|X));
        tick(Select,130);tick(Select|Start,140);assert(actions.empty()); // Judgement ends until release.
        tick(0,150);assert(actions.empty()&&output.back().keys==0);
        // Game: Select held 600 ms without a shortcut is handed over at once.
        output.clear();tick(Select,200);tick(Select,799);assert(!delivered(Select));
        tick(Select,800);assert(output.back().keys==Select);
        tick(Select|Y,810);assert(actions.empty()&&output.back().keys==(Select|Y));
        tick(0,900);assert(output.back().keys==0);
        // A shortcut key up to 80 ms before Select still counts; the game sees it released.
        output.clear();tick(Start,1000);assert(output.back().keys==Start);
        tick(Start|Select,1080);assert(!(output.back().keys&(Start|Select)));
        tick(0,1100);assert(actions.size()==1&&actions[0]==Home);
        policy.setMode(Game);tick(0,1200);actions.clear();output.clear();
        tick(Start,1300);tick(Start|Select,1381);tick(Start,1400);tick(0,1410);assert(actions.empty()); // Too late.
    }
    {
        Policy policy(80);policy.setMode(Game);Sample input,last;std::vector<uint32_t> actions;
        auto tick=[&](uint32_t keys,int64_t now){input.keys=keys;policy.update(input,!keys,now,[&](const Sample &s){last=s;},[&](uint32_t action){actions.push_back(action);});};
        tick(0,0);tick(Select,10);tick(0,20);
        assert(last.keys==Select); // A frame-based consumer must see a short tap after release.
        input.axes={123,-456,789,-1000};tick(X,35);
        assert(last.keys==(Select|X)&&last.axes==input.axes);
        tick(0,69);assert(last.keys==Select);tick(0,70);assert(last.keys==0&&actions.empty());
        tick(Select,100);tick(0,110);policy.setMode(Ui);tick(0,111);assert(last.keys==0);
    }
    for(auto mode:{Ui,Game}) for(auto releaseFirst:{Select,R1}) {
        Policy policy(80);policy.setMode(mode);Sample sample;sample.axes={120,-240,360,-480};
        std::vector<Sample> output;std::vector<uint32_t> actions;
        auto tick=[&](uint32_t keys,int64_t now){sample.keys=keys;policy.update(sample,!keys,now,[&](const Sample &s){output.push_back(s);},[&](uint32_t action){actions.push_back(action);});};
        tick(0,0);tick(Select,10);tick(Select|R1,20);tick(Select|R1,500);
        assert(actions.size()==1&&actions[0]==Diagnostics&&!policy.ownerPending&&!policy.waiting&&policy.mode==mode);
        tick((Select|R1)&~releaseFirst,510);tick(0,520);
        for(const auto &s:output){assert(!(s.keys&(Select|R1)));assert(s.axes==sample.axes);}
        tick(Select,530);tick(Select|R1,540);tick(0,550);assert(actions.size()==2);
        tick(R1,560);assert(output.back().keys==R1);tick(0,570);
        if(mode==Game){tick(Select,600);tick(Select,1200);tick(Select|R1,1210);assert(actions.size()==2&&output.back().keys==(Select|R1));}
    }
    std::puts("INPUT_POLICY_PASS: chords, diagnostics without ownership change, Select hand-over and neutral ownership");
}
