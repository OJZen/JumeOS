#!/usr/bin/env python3
"""Execute the upstream CLI's found-computer branch with a bounded fake HTTP result."""
import argparse
from pathlib import Path
import re
import subprocess

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('source',type=Path)
parser.add_argument('output',type=Path)
parser.add_argument('--qt-prefix')
parser.add_argument('--expect-failure',action='store_true')
args=parser.parse_args()
source=args.source if args.source.is_file() else args.source/'app/cli/listapps.cpp'
text=source.read_text()
body=re.search(r'case Event::ComputerFound:(.*?)\n            break;',text,re.S).group(1)
body=body.replace('QCoreApplication::exit(', 'captureExit(')
args.output.mkdir(parents=True,exist_ok=True)
fixture=r'''
#include <QCoreApplication>
#include <QReadWriteLock>
#include <QString>
#include <QVector>
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
struct NvApp { QString name; };
struct NvComputer { enum { PS_PAIRED=1 }; int pairState=1; QString name="Fixture"; QReadWriteLock lock; QVector<NvApp> appList; };
static QVector<NvApp> serverApps; static int requests=0; static bool unavailable=false;
class NvHTTP { public: explicit NvHTTP(NvComputer*) {} QVector<NvApp> getAppList(){++requests;if(unavailable)throw std::runtime_error("offline");return serverApps;} };
struct Event { NvComputer* computer; };
enum State { StateInit,StateSeekComputer,StateListApp,StateSeekApp,StateFailure };
constexpr int APP_SEEK_TIMEOUT=10000;
struct Timer {void start(int){}};
struct Arguments {bool csv=false;bool isVerbose()const{return false;}bool isPrintCSV()const{return csv;}};
struct Harness {
 State m_State=StateSeekComputer;NvComputer* m_Computer=nullptr;Arguments m_Arguments;Timer timer;Timer* m_TimeoutTimer=&timer;
 int result=999;QVector<NvApp> printed;bool csv=false;
 void captureExit(int value){result=value;}
 void printApps(QVector<NvApp> apps){printed=apps;}
 void printAppsCSV(QVector<NvApp> apps){printed=apps;csv=true;}
 void found(Event event){ BODY }
};
static void check(bool value,const char* message){if(!value){fprintf(stderr,"%s\n",message);std::exit(42);}}
int main(int argc,char**argv){QCoreApplication app(argc,argv);NvComputer computer;
 serverApps={{"Fresh; literal"}};Harness first;first.found({&computer});check(first.result==0&&requests==1&&first.printed.size()==1,"online-empty-cache must fetch and return server apps");
 computer.appList={{"Stale"}};serverApps={{"New name"}};Harness stale;stale.m_Arguments.csv=true;stale.found({&computer});check(stale.result==0&&stale.csv&&stale.printed[0].name=="New name","refresh must not return stale cached entries");
 serverApps.clear();Harness empty;empty.found({&computer});check(empty.result==0&&empty.printed.isEmpty(),"fresh empty response must remain a valid empty list");
 unavailable=true;Harness failed;failed.found({&computer});check(failed.result==1&&failed.m_State==StateFailure&&failed.printed.isEmpty(),"HTTP failure must not be successful empty output");
 computer.pairState=0;const int before=requests;Harness unpaired;unpaired.found({&computer});check(unpaired.result==-1&&requests==before,"unpaired host must not query applications");
 Harness duplicate;duplicate.m_State=StateListApp;duplicate.found({&computer});check(duplicate.result==999&&requests==before,"duplicate host event must not restart lookup");
 puts("MOONLIGHT_LIST_FRESH_HTTP_PASS");}
'''.replace('BODY',body)
(args.output/'check.cpp').write_text(fixture)
(args.output/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.21)\nproject(listcheck LANGUAGES CXX)\nset(CMAKE_CXX_STANDARD 17)\nfind_package(Qt6 REQUIRED COMPONENTS Core)\nadd_executable(listcheck check.cpp)\ntarget_link_libraries(listcheck PRIVATE Qt6::Core)\n')
command=['cmake','-S',str(args.output),'-B',str(args.output/'build')]
if args.qt_prefix:command+=['-DCMAKE_PREFIX_PATH='+args.qt_prefix]
subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
subprocess.run(['cmake','--build',str(args.output/'build'),'-j','2'],check=True,stdout=subprocess.DEVNULL)
r=subprocess.run([str(args.output/'build/listcheck')],capture_output=True,text=True)
if args.expect_failure:
 assert r.returncode==42 and 'online-empty-cache' in r.stderr, r.stderr
 print('BASELINE_LIST_RACE_REPRODUCED')
else:
 assert r.returncode==0,r.stderr
 print(r.stdout.strip())
