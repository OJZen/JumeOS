#include "network.h"
#include <QProcessEnvironment>
#include <QUuid>
#include <QDBusArgument>
#include <QDBusMetaType>
#include <QDBusObjectPath>
#include <QDBusPendingCallWatcher>
#include <QDBusVariant>
#include <QRegularExpression>
#include <QStringDecoder>
#include <algorithm>

namespace {
const QString service="org.freedesktop.NetworkManager";
const QString managerPath="/org/freedesktop/NetworkManager";
const QString properties="org.freedesktop.DBus.Properties";
const QString activeInterface="org.freedesktop.NetworkManager.Connection.Active";
bool objectPath(const QString &value,const QString &kind) {
    return QRegularExpression("^/org/freedesktop/NetworkManager/"+kind+"/[0-9]+$").match(value).hasMatch();
}
bool parseRows(const QByteArray &data,QList<QStringList> *rows) {
    if(data.size()>65536)return false;
    QStringDecoder decoder(QStringDecoder::Utf8);const QString text=decoder.decode(data);
    if(decoder.hasError())return false;
    for(const auto &line:text.split('\n')) {
        if(line.isEmpty())continue;
        QStringList fields;QString field;bool escaped=false;
        for(const auto c:line){
            if(c.unicode()<32||c.unicode()==127)return false;
            if(escaped){if(c!=':'&&c!='\\')return false;field+=c;escaped=false;}
            else if(c=='\\')escaped=true;
            else if(c==':'){fields<<field;field.clear();}
            else field+=c;
        }
        if(escaped)return false;
        fields<<field;rows->append(fields);
    }
    return true;
}
}

NetworkState::NetworkState(bool available,bool controls,QString program,QDBusConnection bus)
    :m_available(available),m_controls(available&&controls),m_program(std::move(program)),m_bus(std::move(bus)) {
    qDBusRegisterMetaType<NetworkSettings>();
    if(m_available&&m_program=="/usr/bin/nmcli"&&!m_bus.isConnected())
        m_bus=QDBusConnection::connectToBus("unix:path=/run/dbus/system_bus_socket","r46h-network-manager");
    m_timer.setSingleShot(true);m_timer.setInterval(12000);
    connect(&m_timer,&QTimer::timeout,this,[this]{m_timeout=true;m_process.kill();});
    connect(&m_process,&QProcess::readyReadStandardOutput,this,[this]{
        m_output+=m_process.readAllStandardOutput();if(m_output.size()>65536){m_overflow=true;m_process.kill();}
    });
    connect(&m_process,&QProcess::readyReadStandardError,this,[this]{m_process.readAllStandardError();});
    connect(&m_process,&QProcess::finished,this,&NetworkState::finish);
    connect(&m_process,&QProcess::errorOccurred,this,[this](QProcess::ProcessError error){
        if(error==QProcess::FailedToStart){m_timer.stop();m_status=QStringLiteral("网络服务不可用。");emit changed();emit notice(m_status);}
    });
    m_connectionTimer.setParent(this);m_connectionTimer.setObjectName("networkConnectionDeadline");
    m_connectionTimer.setSingleShot(true);m_connectionTimer.setInterval(40000);
    connect(&m_connectionTimer,&QTimer::timeout,this,[this]{finishConnection(QStringLiteral("连接请求超时，请刷新确认实际状态；已发送的请求不会自动重试。"));});
    m_signalTimer.setInterval(5000);
    connect(&m_signalTimer,&QTimer::timeout,this,[this]{refreshSignal();});
    if(m_available&&m_program=="/usr/bin/nmcli")m_signalTimer.start();
    if(m_available)refresh();
}
NetworkState::~NetworkState(){
    m_timer.stop();m_connectionTimer.stop();m_signalTimer.stop();m_connecting=false;clearPassword();
    m_process.disconnect(this);
    if(m_process.state()!=QProcess::NotRunning){m_process.kill();m_process.waitForFinished(1000);}
}
bool NetworkState::parse(const QByteArray &data,QVariantList *profiles) {
    QList<QStringList> rows;if(!parseRows(data,&rows))return false;
    QVariantList result;QStringList ids;
    for(const auto &fields:rows) {
        if(fields.size()!=4)return false;
        if(fields[1]!="802-11-wireless"&&fields[1]!="wifi")continue;
        const auto id=QUuid(fields[0]);
        if(id.isNull() || fields[2].isEmpty() || fields[2].size()>256 || result.size()>=64 || ids.contains(fields[0]))return false;
        ids<<fields[0];result.append(QVariantMap{{"id",fields[0]},{"name",fields[2]},{"active",!fields[3].isEmpty()&&fields[3]!="--"}});
    }
    *profiles=result;return true;
}
int NetworkState::parseSignal(const QByteArray &data) {
    QList<QStringList> rows;if(!parseRows(data,&rows))return -1;
    int result=-1;
    for(const auto &fields:rows){
        if(fields.size()!=2)return -1;
        if(fields[0]!="*")continue;
        bool ok=false;const int value=fields[1].toInt(&ok);
        if(result>=0||!ok||value<0||value>100)return -1;
        result=value;
    }
    return result;
}
bool NetworkState::parseAccessPoints(const QByteArray &data,QVariantList *accessPoints) {
    QList<QStringList> rows;if(!parseRows(data,&rows)||rows.size()>256)return false;
    QVariantList result;QStringList paths;
    for(const auto &f:rows){
        if(f.size()!=7)return false;
        if(f[2].isEmpty()||f[2]=="--")continue; // Hidden/non-text SSIDs need a separate entry flow.
        bool ok=false;const int strength=f[3].toInt(&ok);
        if(!objectPath(f[0],"AccessPoint")||paths.contains(f[0])||!ok||strength<0||strength>100||f[2].toUtf8().size()>32
           ||!QRegularExpression("^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$").match(f[1]).hasMatch()
           ||!QRegularExpression("^[A-Za-z0-9_.-]{1,15}$").match(f[5]).hasMatch()
           ||!(f[6].isEmpty()||f[6]=="--"||f[6]=="*"))return false;
        QString security="unsupported";
        if(f[4].isEmpty()||f[4]=="--")security="open";
        else if(QRegularExpression("^WPA[12](?: WPA[12])?$").match(f[4]).hasMatch())security="psk";
        paths<<f[0];result.append(QVariantMap{{"path",f[0]},{"bssid",f[1].toUpper()},{"ssid",f[2]},
            {"signal",strength},{"security",security},{"interface",f[5]},{"active",f[6]=="*"}});
    }
    std::stable_sort(result.begin(),result.end(),[](const QVariant &a,const QVariant &b){return a.toMap().value("signal").toInt()>b.toMap().value("signal").toInt();});
    QVariantList unique;QStringList seen;
    for(const auto &value:result){const auto ap=value.toMap();const auto key=ap.value("ssid").toString()+QChar(0)+ap.value("security").toString()+QChar(0)+ap.value("interface").toString();if(!seen.contains(key)){seen<<key;unique<<value;}}
    *accessPoints=unique;return true;
}
bool NetworkState::validPassword(const QString &value) {
    return QRegularExpression("\\A(?:[\\x20-\\x7e]{8,63}|[0-9A-Fa-f]{64})\\z").match(value).hasMatch();
}
void NetworkState::setRemember(bool value){if(!m_controls||busy()||m_remember==value)return;m_remember=value;emit changed();}
bool NetworkState::fail(const QString &text){m_status=text;emit changed();emit notice(text);return false;}
bool NetworkState::scan(){return start("scan",{"--fields","DBUS-PATH,BSSID,SSID,SIGNAL,SECURITY,DEVICE,IN-USE","device","wifi","list","--rescan","yes"});}
bool NetworkState::selectAccessPoint(int index){
    if(!m_controls||busy()||index<0||index>=m_accessPoints.size())return false;
    const auto value=m_accessPoints[index].toMap();
    if(value.value("security")=="unsupported")return fail(QStringLiteral("暂不支持此网络的认证方式，请使用已保存的配置。"));
    m_selectedNetwork=value;emit changed();return true;
}
bool NetworkState::start(const QString &operation,const QStringList &arguments) {
    if(!m_available||busy())return false;
    m_output.clear();m_timeout=m_overflow=false;m_operation=operation;
    if(operation!="signal")m_status=operation=="list"?QStringLiteral("正在读取网络…"):operation=="scan"?QStringLiteral("正在扫描 Wi-Fi…"):QStringLiteral("正在更新网络…");
    auto env=QProcessEnvironment::systemEnvironment();env.insert("LC_ALL","C.UTF-8");
    QStringList options{"--terse","--escape","yes","--colors","no","--wait","10"};options.append(arguments);
    m_process.setProcessEnvironment(env);m_process.start(m_program,options);
    m_timer.start();if(operation!="signal")emit changed();return true;
}
bool NetworkState::refresh(){return start("list",{"--fields","UUID,TYPE,NAME,DEVICE","connection","show"});}
bool NetworkState::refreshSignal(){return start("signal",{"--fields","IN-USE,SIGNAL","device","wifi","list","ifname","wlan0","--rescan","no"});}
bool NetworkState::activate(const QString &uuid) {
    if(!m_controls)return false;
    bool known=false;for(const auto &p:m_profiles)if(p.toMap().value("id").toString()==uuid)known=true;
    if(!known)return false;
    return start("up",{"connection","up","uuid",uuid});
}
bool NetworkState::disconnect() {
    if(!m_controls)return false;
    QString id;for(const auto &p:m_profiles)if(p.toMap().value("active").toBool()){if(!id.isEmpty())return false;id=p.toMap().value("id").toString();}
    return !id.isEmpty() && start("down",{"connection","down","uuid",id});
}
bool NetworkState::forget(const QString &uuid){
    if(!m_controls)return false;
    for(const auto &p:m_profiles)if(p.toMap().value("id").toString()==uuid)return start("forget",{"connection","delete","uuid",uuid});
    return false;
}
void NetworkState::finish(int code,QProcess::ExitStatus exit) {
    m_timer.stop();m_output+=m_process.readAllStandardOutput();const auto operation=m_operation;
    if(operation=="signal"){
        const int value=!m_timeout&&!m_overflow&&exit==QProcess::NormalExit&&code==0?parseSignal(m_output):-1;
        if(value!=m_signal){m_signal=value;emit changed();}
        return;
    }
    if(m_timeout)m_status=QStringLiteral("网络请求超时；请刷新确认实际状态。");
    else if(m_overflow||m_output.size()>65536)m_status=QStringLiteral("网络状态超出读取范围。");
    else if(exit!=QProcess::NormalExit||code!=0)m_status=QStringLiteral("网络操作失败，请检查设备连接和权限。");
    else if(operation=="scan"){
        QVariantList values;
        if(parseAccessPoints(m_output,&values)){m_accessPoints=values;m_selectedNetwork.clear();m_status=QStringLiteral("发现 %1 个 Wi-Fi 网络").arg(values.size());emit changed();emit scanReady();return;}
        m_status=QStringLiteral("无法解析扫描结果。");
    }else if(operation=="list"){
        QVariantList values;
        if(parse(m_output,&values)){m_profiles=values;m_status=QStringLiteral("已保存 %1 个 Wi-Fi 配置").arg(values.size());emit changed();return;}
        m_status=QStringLiteral("无法解析网络状态。");
    }else{emit changed();refresh();return;}
    emit changed();emit notice(m_status);
}

void NetworkState::clearPassword(){m_password.fill('\0');m_password.clear();}
void NetworkState::busCall(const QString &path,const QString &interface,const QString &method,
                           const QVariantList &arguments,std::function<void(const QList<QVariant> &)> done){
    auto message=QDBusMessage::createMethodCall(service,path,interface,method);message.setArguments(arguments);
    const auto generation=m_connectionGeneration;
    auto *watcher=new QDBusPendingCallWatcher(m_bus.asyncCall(message,5000),this);
    connect(watcher,&QDBusPendingCallWatcher::finished,this,[this,watcher,generation,done=std::move(done)]{
        const auto reply=watcher->reply();watcher->deleteLater();
        if(!m_connecting||generation!=m_connectionGeneration)return;
        if(reply.type()==QDBusMessage::ErrorMessage){finishConnection(QStringLiteral("网络服务拒绝或未完成请求，请检查权限并刷新连接状态。"));return;}
        done(reply.arguments());
    });
}
bool NetworkState::connectSelected(const QString &password){
    if(!m_controls||busy()||m_selectedNetwork.isEmpty())return false;
    const bool secure=m_selectedNetwork.value("security")=="psk";
    if((secure&&!validPassword(password))||(!secure&&!password.isEmpty()))
        return fail(QStringLiteral("密码需为 8–63 位可打印 ASCII 字符，或 64 位十六进制密钥。"));
    if(!m_bus.isConnected())return fail(QStringLiteral("本机网络服务不可用。"));
    if(m_profiles.size()>=64)return fail(QStringLiteral("已保存配置过多，请先移除不再使用的网络。"));
    m_connecting=true;++m_connectionGeneration;m_password=password.toUtf8();
    m_status=QStringLiteral("正在连接 Wi-Fi…");m_connectionTimer.start();emit changed();
    busCall(m_selectedNetwork.value("path").toString(),properties,"GetAll",{service+".AccessPoint"},[this,secure](const QList<QVariant> &args){
        const auto ap=args.size()==1?qdbus_cast<QVariantMap>(args[0]):QVariantMap();
        const auto flags=ap.value("Flags"),wpa=ap.value("WpaFlags"),rsn=ap.value("RsnFlags");
        const uint security=wpa.toUInt()|rsn.toUInt();
        // NM security flags: PSK=0x100, enterprise=0x200; open must not advertise privacy.
        const bool securityMatches=secure?(security&0x100)&&!(security&0x200):security==0&&(flags.toUInt()&1)==0;
        if(ap.value("Mode").toUInt()!=2||flags.metaType().id()!=QMetaType::UInt||wpa.metaType().id()!=QMetaType::UInt||rsn.metaType().id()!=QMetaType::UInt||!securityMatches
           ||ap.value("Ssid").toByteArray()!=m_selectedNetwork.value("ssid").toString().toUtf8()
           ||ap.value("HwAddress").toString().toUpper()!=m_selectedNetwork.value("bssid").toString()){
            finishConnection(QStringLiteral("网络信息已变化，请重新扫描后连接。"));return;
        }
        busCall(managerPath,service,"GetDeviceByIpIface",{m_selectedNetwork.value("interface")},[this,secure](const QList<QVariant> &args){
            const auto device=args.size()==1?args[0].value<QDBusObjectPath>().path():QString();
            if(!objectPath(device,"Devices")){finishConnection(QStringLiteral("无线设备不可用。"));return;}
            NetworkSettings settings{{"connection",{{"id",QStringLiteral("R46H ")+m_selectedNetwork.value("ssid").toString()},
                {"uuid",QUuid::createUuid().toString(QUuid::WithoutBraces)},{"type","802-11-wireless"},{"autoconnect",m_remember}}},
                {"802-11-wireless",{{"ssid",m_selectedNetwork.value("ssid").toString().toUtf8()},{"mode","infrastructure"}}},
                {"ipv4",{{"method","auto"}}},{"ipv6",{{"method","auto"}}}};
            if(secure)settings["802-11-wireless-security"]={{"key-mgmt","wpa-psk"},{"psk",QString::fromUtf8(m_password)}};
            clearPassword();
            busCall(managerPath,service,"AddAndActivateConnection2",{QVariant::fromValue(settings),QVariant::fromValue(QDBusObjectPath(device)),
                QVariant::fromValue(QDBusObjectPath(m_selectedNetwork.value("path").toString())),QVariantMap{{"persist",m_remember?"disk":"volatile"}}},[this](const QList<QVariant> &args){
                m_activePath=args.size()==3?args[1].value<QDBusObjectPath>().path():QString();
                if(!objectPath(m_activePath,"ActiveConnection")||!m_bus.connect(service,m_activePath,activeInterface,"StateChanged",this,SLOT(activeStateChanged(uint,uint,QDBusMessage)))){
                    finishConnection(QStringLiteral("请求已发送，但无法跟踪连接状态，请刷新确认。"));return;
                }
                // Read after subscribing so an immediate transition cannot be missed.
                busCall(m_activePath,properties,"Get",{activeInterface,"State"},[this](const QList<QVariant> &args){
                    const auto state=args.size()==1?args[0].value<QDBusVariant>().variant():QVariant();
                    if(state.metaType().id()!=QMetaType::UInt){finishConnection(QStringLiteral("连接状态不可用，请刷新确认。"));return;}
                    handleActiveState(state.toUInt());
                });
            });
        });
    });
    return true;
}
void NetworkState::activeStateChanged(uint state,uint reason,const QDBusMessage &message){
    Q_UNUSED(reason);
    if(message.path()==m_activePath)handleActiveState(state);
}
void NetworkState::handleActiveState(uint state){
    if(!m_connecting)return;
    if(state==2)finishConnection(QStringLiteral("Wi-Fi 已连接。"),true);
    else if(state==4)finishConnection(QStringLiteral("连接未建立，请检查密码、信号和设备权限。"));
}
void NetworkState::finishConnection(const QString &message,bool connected){
    m_connectionTimer.stop();m_connecting=false;clearPassword();
    if(!m_activePath.isEmpty())m_bus.disconnect(service,m_activePath,activeInterface,"StateChanged",this,SLOT(activeStateChanged(uint,uint,QDBusMessage)));
    m_activePath.clear();m_status=message;emit changed();emit notice(message);
    if(connected)refresh();
}
