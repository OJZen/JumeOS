#include "device.h"
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QProcess>
#include <QRegularExpression>
#include <QSysInfo>
#include <cmath>
#include <fcntl.h>
#include <unistd.h>

namespace {
QString read(const QString &root, const QString &name) {
    QFile file(QDir(root).filePath(name));
    return file.open(QIODevice::ReadOnly) ? QString::fromUtf8(file.read(65536)).trimmed() : QString();
}
qlonglong number(const QString &text) {
    bool ok=false;const auto value=text.toLongLong(&ok);return ok ? value : -1;
}
QStringList words(const QString &text) { return text.split(QRegularExpression("\\s+"),Qt::SkipEmptyParts); }
int wirelessSignal(const QString &text) {
    for(const auto &line:text.split('\n')){
        const auto fields=words(line);bool ok=false;
        if(fields.size()<3 || fields[0]!="wlan0:")continue;
        const double quality=fields[2].toDouble(&ok);
        return ok && quality>=0 ? qBound(0,qRound(quality*100./70.),100) : -1;
    }
    return -1;
}
bool identity(const QString &root) {
#ifdef Q_OS_LINUX
    if(root!="/" || read(root,"proc/sys/kernel/osrelease")!="6.12.99-r46h-mainline-v0.15-gaming-product"
       || read(root,"sys/class/block/mmcblk0/device/cid")!="fe343253440000002000002d57019567"
       || read(root,"sys/class/block/mmcblk0/size")!="122138624")return false;
    QProcess process;process.start("/usr/bin/findmnt",{"-rn","-o","UUID","/"});
    if(!process.waitForFinished(500)){process.kill();process.waitForFinished();return false;}
    const auto uuid=process.readAllStandardOutput().trimmed();
    return process.exitCode()==0 && (uuid=="d3130017-46a4-4d56-9001-000000000017"
                                    || uuid=="d3130018-46a4-4d56-9001-000000000018");
#else
    Q_UNUSED(root);return false;
#endif
}
}

QVariantMap DeviceState::snapshot(const QString &root) {
    QVariantMap result, memory;
    for(const auto &line:read(root,"proc/meminfo").split('\n')) {
        const auto fields=words(line);
        if(fields.size()==3 && fields[2]=="kB")memory[fields[0].chopped(1)]=number(fields[1]);
    }
    for(const auto &key:{"MemTotal","MemAvailable","SwapTotal","SwapFree"})
        result[key]=memory.value(key,-1);
    QVariantList policies;
    const QString base="sys/devices/system/cpu/cpufreq";
    for(const auto &name:QDir(QDir(root).filePath(base)).entryList({"policy*"},QDir::Dirs|QDir::NoDotAndDotDot,QDir::Name)) {
        if(!QRegularExpression("^policy[0-9]+$").match(name).hasMatch())continue;
        const auto prefix=base+"/"+name+"/";QVariantMap policy{{"name",name}};
        policy["governor"]=read(root,prefix+"scaling_governor");
        policy["governors"]=words(read(root,prefix+"scaling_available_governors"));
        QVariantList frequencies;
        for(const auto &value:words(read(root,prefix+"scaling_available_frequencies")))
            if(number(value)>0 && number(value)<=10000000)frequencies.append(number(value));
        policy["frequencies"]=frequencies;
        for(const auto &key:{"scaling_cur_freq","scaling_min_freq","scaling_max_freq","cpuinfo_min_freq","cpuinfo_max_freq"})
            policy[key]=number(read(root,prefix+key));
        policies.append(policy);
    }
    result["policies"]=policies;
    result["cpu"]=policies.size()==1 ? policies.first().toMap() : QVariantMap();
    const QString light="sys/class/backlight/backlight/";
    result["brightnessRaw"]=number(read(root,light+"brightness"));
    result["brightnessActual"]=number(read(root,light+"actual_brightness"));
    result["brightnessMax"]=number(read(root,light+"max_brightness"));
    const auto maximum=result["brightnessMax"].toLongLong(),level=result["brightnessRaw"].toLongLong();
    result["brightnessPercent"]=maximum>0 && level>=0 && level<=maximum ? qRound(100.*level/maximum) : -1;
    const QString battery="sys/class/power_supply/rk817-battery/";
    result["voltageUv"]=number(read(root,battery+"voltage_avg"));
    if(result["voltageUv"].toLongLong()<0)result["voltageUv"]=number(read(root,battery+"voltage_now"));
    result["minimumVoltageUv"]=number(read(root,battery+"voltage_min_design"));
    result["batteryStatus"]=read(root,battery+"status");
    result["capacity"]=number(read(root,battery+"capacity"));
    result["online"]=number(read(root,"sys/class/power_supply/rk817-charger/online"));
    result["wifiSignal"]=wirelessSignal(read(root,"proc/net/wireless"));
    result["lowVoltage"]=result["minimumVoltageUv"].toLongLong()>0 && result["voltageUv"].toLongLong()>0
        && result["voltageUv"].toLongLong()<result["minimumVoltageUv"].toLongLong();
    double temperature=-1,socTemperature=-1;bool hot=false;
    for(const auto &name:QDir(QDir(root).filePath("sys/class/thermal")).entryList({"thermal_zone*"},QDir::Dirs|QDir::NoDotAndDotDot)) {
        const auto prefix="sys/class/thermal/"+name+"/";const auto value=number(read(root,prefix+"temp"));
        if(value<0 || value>200000)continue;
        temperature=qMax(temperature,value/1000.);
        if(read(root,prefix+"type")=="soc-thermal")socTemperature=value/1000.;
        for(const auto &trip:QDir(QDir(root).filePath(prefix)).entryList({"trip_point_*_type"},QDir::Files)) {
            const auto type=read(root,prefix+trip);const auto limit=number(read(root,prefix+QString(trip).replace("_type","_temp")));
            if((type=="hot" || type=="critical") && limit>5000 && value>=limit-5000)hot=true;
        }
    }
    result["temperatureC"]=temperature;result["socTemperatureC"]=socTemperature;result["hot"]=hot;
    QVariantList cpuCooling,gpuCooling;
    for(const auto &name:QDir(QDir(root).filePath("sys/class/thermal")).entryList({"cooling_device*"},QDir::Dirs|QDir::NoDotAndDotDot)){
        const auto prefix="sys/class/thermal/"+name+"/";const auto type=read(root,prefix+"type");
        if(type=="cpufreq-cpu0")cpuCooling.append(number(read(root,prefix+"cur_state")));
        if(type.startsWith("devfreq-")&&type.endsWith(".gpu"))gpuCooling.append(number(read(root,prefix+"cur_state")));
    }
    result["cpuCoolingState"]=cpuCooling.size()==1?cpuCooling.first():QVariant(-1);
    result["gpuCoolingState"]=gpuCooling.size()==1?gpuCooling.first():QVariant(-1);
    QVariantList gpuFrequencies;
    for(const auto &name:QDir(QDir(root).filePath("sys/class/devfreq")).entryList(QDir::Dirs|QDir::NoDotAndDotDot))
        if(name.contains("gpu",Qt::CaseInsensitive))gpuFrequencies.append(number(read(root,"sys/class/devfreq/"+name+"/cur_freq")));
    result["gpuFrequencyHz"]=gpuFrequencies.size()==1 ? gpuFrequencies.first() : QVariant(-1);
    const auto levelSaved=number(read(root,"var/lib/r46h-volume/level"));
    result["volumeSaved"]=levelSaved>=0 && levelSaved<=201 ? qRound(levelSaved*100./201) : -1;
    QVariantList swaps;
    const auto swapLines=read(root,"proc/swaps").split('\n');
    for(int i=1;i<swapLines.size();++i){const auto fields=words(swapLines[i]);if(fields.size()==5)swaps.append(QVariantMap{{"type",fields[1]},{"sizeKiB",number(fields[2])},{"usedKiB",number(fields[3])}});}
    result["swaps"]=swaps;
    result["zramPresent"]=QFileInfo::exists(QDir(root).filePath("sys/block/zram0/comp_algorithm"));
    result["zramAlgorithms"]=read(root,"sys/block/zram0/comp_algorithm");
    result["zramSize"]=number(read(root,"sys/block/zram0/disksize"));
    const auto stats=words(read(root,"sys/block/zram0/mm_stat"));
    result["zramOriginal"]=number(stats.value(0));result["zramCompressed"]=number(stats.value(1));result["zramMemory"]=number(stats.value(2));
    const auto pressure=QRegularExpression("(?:^| )avg10=([0-9]+(?:\\.[0-9]+)?)").match(read(root,"proc/pressure/memory").section('\n',0,0));
    result["memoryPressurePercent"]=pressure.hasMatch() ? pressure.captured(1).toDouble() : -1;
    return result;
}

DeviceState::DeviceState(QString root, bool allowControls, bool fixture):m_root(QDir(root).absolutePath()) {
    connect(&m_volumeWatcher,&QFileSystemWatcher::fileChanged,this,&DeviceState::volumeFileChanged);
    connect(&m_volumeWatcher,&QFileSystemWatcher::directoryChanged,this,&DeviceState::volumeFileChanged);
    m_target=(fixture && m_root!="/") || identity(m_root);m_controls=allowControls && m_target;
    refresh();refreshStorage();m_originalCpu=m_info.value("cpu").toMap();m_warned=false;
    m_timer.setInterval(2000);connect(&m_timer,&QTimer::timeout,this,&DeviceState::refresh);
    if(m_target)m_timer.start();
}
DeviceState::~DeviceState(){if(m_beforeDim>=0)setDimmed(false);}
QString DeviceState::path(const QString &relative) const {return QDir(m_root).filePath(relative);}
bool DeviceState::fail(const QString &text){m_error=text;emit changed();return false;}
void DeviceState::watchVolume() {
    const auto directory=path("var/lib/r46h-volume"), file=directory+"/level";
    if(QFileInfo::exists(directory) && !m_volumeWatcher.directories().contains(directory))m_volumeWatcher.addPath(directory);
    if(QFileInfo::exists(file) && !m_volumeWatcher.files().contains(file))m_volumeWatcher.addPath(file);
}
void DeviceState::volumeFileChanged(const QString &name) {
    const auto file=path("var/lib/r46h-volume/level");
    // Ignore the service's temporary files. Its atomic rename drops the file watch;
    // rearm it, including after removal/recreation. Equal values still mean a key press.
    if(name!=file && m_volumeWatcher.files().contains(file))return;
    watchVolume();
    const auto raw=number(read(m_root,"var/lib/r46h-volume/level"));
    if(raw<0 || raw>201)return;
    const int percent=qRound(raw*100./201);
    if(m_info.value("volumeSaved").toInt()!=percent){m_info["volumeSaved"]=percent;emit changed();}
    emit volumeChanged(percent);
}
void DeviceState::refresh() {
    if(!m_target)return;
    watchVolume();
    auto next=snapshot(m_root);
    m_sampleClock.start();
    const auto fields=words(read(m_root,"proc/stat").section('\n',0,0));
    qulonglong total=0,idle=0;bool valid=fields.size()>=9 && fields[0]=="cpu";
    for(int i=1;i<=8 && valid;++i){bool ok=false;const auto n=fields[i].toULongLong(&ok);valid=ok;total+=n;if(i==4||i==5)idle+=n;}
    next["systemCpu"]=valid && total==m_ticks ? m_info.value("systemCpu",-1)
        : QVariant(valid && total>m_ticks && idle>=m_idle && m_ticks>0 ? qBound(0.,100.*(1.-double(idle-m_idle)/double(total-m_ticks)),100.) : -1);
    m_ticks=valid?total:0;m_idle=valid?idle:0;
    const bool warn=next.value("lowVoltage").toBool() || next.value("hot").toBool();
    if(next!=m_info){m_info=next;emit changed();}
    if(warn && !m_warned)emit warning(next.value("lowVoltage").toBool()?QStringLiteral("电池电压偏低，请连接电源并结束高负载任务。"):QStringLiteral("温度接近内核保护阈值，请结束高负载任务。"));
    m_warned=warn;
}
QVariantMap DeviceState::diagnostics() const {
    QVariantMap result{{"target",target()},{"controls",controls()}};
    if(!target())return result;
    result["sampleAgeMs"]=m_sampleClock.isValid()?m_sampleClock.elapsed():-1;
    // Explicit numeric allowlist: no profile names, addresses, paths or credentials.
    for(const auto *key:{"systemCpu","MemTotal","MemAvailable","SwapTotal","SwapFree","temperatureC","socTemperatureC","cpuCoolingState","gpuCoolingState","gpuFrequencyHz",
                        "voltageUv","minimumVoltageUv","capacity","online","wifiSignal","brightnessRaw","brightnessActual","brightnessMax",
                        "brightnessPercent","memoryPressurePercent","zramSize","zramOriginal","zramCompressed","zramMemory"})
        result[key]=m_info.value(key,-1);
    result["lowVoltage"]=m_info.value("lowVoltage",false);result["hot"]=m_info.value("hot",false);
    const auto cpu=m_info.value("cpu").toMap();
    for(const auto *key:{"scaling_cur_freq","scaling_min_freq","scaling_max_freq"})result[key]=cpu.value(key,-1);
    return result;
}
QVariantMap DeviceState::storageInfo(const QString &label,const QStorageInfo &info,const QString &expectedMount) {
    const bool available=info.isValid()&&info.isReady()&&info.rootPath()==expectedMount;
    return {{"label",label},{"available",available},{"readOnly",available&&info.isReadOnly()},
        {"totalBytes",available?info.bytesTotal():-1},{"availableBytes",available?info.bytesAvailable():-1},
        {"filesystem",available?QString::fromLatin1(info.fileSystemType()):QString()}};
}
void DeviceState::refreshStorage() {
    if(!target())return;
    QVariantList next;
    for(const auto &entry:QList<QPair<QString,QString>>{{QStringLiteral("系统分区"),"/"},{QStringLiteral("游戏分区"),"/roms"},{QStringLiteral("启动分区"),"/boot"}}){
        const auto mount=m_root=="/"?entry.second:path(entry.second.mid(1));
        next.append(storageInfo(entry.first,QStorageInfo(mount),mount));
    }
    if(next!=m_storage){m_storage=next;emit changed();}
}
bool DeviceState::writeValue(const QString &relative,const QString &value) {
    const auto encoded=QFile::encodeName(path(relative));const auto bytes=(value+'\n').toUtf8();
    const int fd=::open(encoded.constData(),O_WRONLY|O_TRUNC|O_CLOEXEC|O_NOFOLLOW);
    if(fd<0)return false;const auto done=::write(fd,bytes.constData(),size_t(bytes.size()));::close(fd);
    if(done!=bytes.size())return false;
    // CPUFreq QoS updates policy limits in deferred work: an immediate read can still be old.
    const bool deferred=relative.endsWith("scaling_min_freq")||relative.endsWith("scaling_max_freq");
    QElapsedTimer deadline;deadline.start();
    while(read(m_root,relative)!=value){
        if(!deferred||deadline.elapsed()>=100)return false;
        ::usleep(2000);
    }
    return true;
}
bool DeviceState::setBrightness(int percent) {
    if(!controls() || percent<10 || percent>100)return fail(QStringLiteral("亮度控制尚不可用。"));
    refresh();const int maximum=m_info.value("brightnessMax").toInt();const int old=m_info.value("brightnessRaw").toInt();
    if(maximum<=0 || maximum>65535 || old<0 || old>maximum)return fail(QStringLiteral("无法读取背光范围。"));
    const int level=qMax(1,qRound(maximum*percent/100.));
    if(!writeValue("sys/class/backlight/backlight/brightness",QString::number(level))){
        if(!writeValue("sys/class/backlight/backlight/brightness",QString::number(old)))m_controls=false;
        refresh();return fail(QStringLiteral("背光写入或读回失败；请检查设备权限。"));
    }
    m_beforeDim=-1;m_error.clear();refresh();emit changed();return true;
}
bool DeviceState::setDimmed(bool dimmed) {
    if(!controls())return false;
    if(dimmed && m_beforeDim<0){
        const int old=int(number(read(m_root,"sys/class/backlight/backlight/brightness")));
        if(old<1)return fail(QStringLiteral("无法读取当前背光。"));
        m_beforeDim=old;
        if(!writeValue("sys/class/backlight/backlight/brightness",QString::number(qMax(1,old/4)))){
            if(writeValue("sys/class/backlight/backlight/brightness",QString::number(old)))m_beforeDim=-1;
            else m_controls=false;
            return fail(QStringLiteral("背光变暗失败。"));
        }
    }else if(!dimmed && m_beforeDim>=0){
        if(!writeValue("sys/class/backlight/backlight/brightness",QString::number(m_beforeDim)))return fail(QStringLiteral("背光恢复失败，请通过串口恢复。"));
        m_beforeDim=-1;
    }
    refresh();return true;
}
bool DeviceState::writeCpu(const QVariantMap &policy,const QString &governor,int minimum,int maximum) {
    const QString prefix="sys/devices/system/cpu/cpufreq/"+policy.value("name").toString()+"/";
    const auto currentMin=number(read(m_root,prefix+"scaling_min_freq"));
    // Widen before narrowing, preserving min <= max at every write.
    if(maximum<currentMin){if(!writeValue(prefix+"scaling_min_freq",QString::number(minimum)) || !writeValue(prefix+"scaling_max_freq",QString::number(maximum)))return false;}
    else if(!writeValue(prefix+"scaling_max_freq",QString::number(maximum)) || !writeValue(prefix+"scaling_min_freq",QString::number(minimum)))return false;
    return writeValue(prefix+"scaling_governor",governor);
}
bool DeviceState::applyCpu(QString governor,int minimum,int maximum) {
    if(!controls())return fail(QStringLiteral("CPU 控制尚不可用。"));refresh();
    if(m_info.value("lowVoltage").toBool() || m_info.value("hot").toBool() || m_info.value("temperatureC").toDouble()<0
       || m_info.value("online").toInt()!=1 || m_info.value("voltageUv").toLongLong()<=0 || m_info.value("minimumVoltageUv").toLongLong()<=0)
        return fail(QStringLiteral("当前电压或温度不适合调整 CPU。"));
    const auto cpu=m_info.value("cpu").toMap();const auto frequencies=cpu.value("frequencies").toList();
    if(cpu.value("name").toString()!="policy0" || !cpu.value("governors").toStringList().contains(governor)
       || minimum<=0 || maximum<minimum || minimum<cpu.value("cpuinfo_min_freq").toInt() || maximum>cpu.value("cpuinfo_max_freq").toInt()
       || (!frequencies.isEmpty() && (!frequencies.contains(QVariant::fromValue<qlonglong>(minimum)) || !frequencies.contains(QVariant::fromValue<qlonglong>(maximum)))))
        return fail(QStringLiteral("CPU 配置不在设备支持范围内。"));
    if(!writeCpu(cpu,governor,minimum,maximum)) {
        const bool restored=writeCpu(cpu,cpu.value("governor").toString(),cpu.value("scaling_min_freq").toInt(),cpu.value("scaling_max_freq").toInt());
        if(!restored)m_controls=false;refresh();return fail(restored?QStringLiteral("CPU 调整失败，已恢复原配置。"):QStringLiteral("CPU 恢复失败，已禁用写入，请通过串口检查。"));
    }
    m_error.clear();refresh();emit changed();return true;
}
bool DeviceState::cpuPreset(const QString &name) {
    if(m_originalCpu.isEmpty())return fail(QStringLiteral("原始 CPU 配置不可用。"));
    const auto governor=name=="original"?m_originalCpu.value("governor").toString():name=="balanced"?QString("schedutil"):name=="performance"?QString("performance"):name=="powersave"?QString("powersave"):QString();
    return applyCpu(governor,m_originalCpu.value("scaling_min_freq").toInt(),m_originalCpu.value("scaling_max_freq").toInt());
}
bool DeviceState::requestPower(const QString &action) {
    if(!controls() || (action!="poweroff" && action!="reboot"))return fail(QStringLiteral("电源操作尚不可用。"));
    emit powerRequested(action=="poweroff"?77:78);return true;
}
