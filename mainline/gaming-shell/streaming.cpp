#include "streaming.h"
#include "streamstats.h"
#include <QCryptographicHash>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QHostAddress>
#include <QJsonArray>
#include <QJsonDocument>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QRandomGenerator>
#include <QRegularExpression>
#include <QSaveFile>
#include <QSettings>
#include <QSet>
#include <QUuid>
#include <QUrlQuery>
#include <QXmlStreamReader>
#include <QStringDecoder>
#include <sys/stat.h>
#include <unistd.h>
#include <cerrno>

namespace {
bool textValue(const QString &text, int limit) { return !text.isEmpty() && text.size() <= limit && !text.contains(QRegularExpression("[\\x00-\\x1f\\x7f]")); }
bool privateFile(const QString &path, bool allowMissing = false) {
    struct stat st{};
    if (::lstat(QFile::encodeName(path).constData(), &st) != 0) return allowMissing && errno == ENOENT;
    return S_ISREG(st.st_mode) && st.st_uid == geteuid() && (st.st_mode & 077) == 0;
}
bool validHost(const QJsonObject &h) {
    for (auto it=h.begin();it!=h.end();++it) if(!QStringList{"id","name","address","application","preset","overlay","paired"}.contains(it.key()))return false;
    return !QUuid(h.value("id").toString()).isNull() && textValue(h.value("name").toString(), 64)
        && !h.value("address").toString().isEmpty() && Streaming::validAddress(h.value("address").toString()) == h.value("address").toString() && textValue(h.value("application").toString(), 128)
        && h.value("preset").isDouble() && QList<QJsonValue>{0,1,2}.contains(h.value("preset"))
        && h.value("overlay").isBool() && h.value("paired").isBool();
}
}
Streaming::Streaming(QString state, QObject *parent) : QObject(parent), m_directory(QDir(state).filePath("streaming")) {
    m_statisticsExpiry.setSingleShot(true); m_statisticsExpiry.setInterval(2500);
    connect(&m_statisticsExpiry, &QTimer::timeout, this, [this] { setStatisticsActive(m_statistics.value("active").toBool()); });
    QFile file(m_directory + "/hosts.json");
    struct stat fileInfo{};const int exists=::lstat(QFile::encodeName(file.fileName()).constData(),&fileInfo);
    if(exists!=0&&errno!=ENOENT&&errno!=ENOTDIR){m_loadFailed=true;fail(QStringLiteral("无法读取主机列表，原文件已保留。"));}
    if (exists==0) {
        if (!privateFile(file.fileName()) || !file.open(QIODevice::ReadOnly) || file.size() > 32768) { m_loadFailed = true; fail(QStringLiteral("无法读取主机列表，原文件已保留。")); }
        else {
            const auto d = QJsonDocument::fromJson(file.readAll()); const auto root = d.object(); QSet<QString> ids;
            bool valid = d.isObject() && root.value("version") == QJsonValue(1) && root.value("hosts").isArray() && root.value("hosts").toArray().size() <= 32;
            for (const auto &v : root.value("hosts").toArray()) {
                auto h=v.toObject(); auto id=h.value("id").toString();
                if (!validHost(h) || ids.contains(id)) valid=false;
                ids.insert(id); m_hosts.append(h);
            }
            if (!valid) { m_loadFailed=true; m_hosts.clear(); fail(QStringLiteral("主机列表格式异常，原文件已保留。")); }
            else for (int i=0;i<m_hosts.size();++i) if(m_hosts[i].value("id")==root.value("selected")) m_selected=i;
        }
    }
    QFile result(m_directory + "/result.json");
    if (privateFile(result.fileName()) && result.open(QIODevice::ReadOnly) && result.size() <= 4096) {
        const auto r=QJsonDocument::fromJson(result.readAll()).object();
        if(r.value("version")==QJsonValue(1)) m_status=r.value("exit").toInt(-1)==0 ? QStringLiteral("串流已结束") : QStringLiteral("上次连接未正常结束，可重新连接");
    }
    m_pair.setStandardInputFile(QProcess::nullDevice()); m_pair.setStandardOutputFile(QProcess::nullDevice()); m_pair.setStandardErrorFile(QProcess::nullDevice());
    m_pairTimer.setSingleShot(true); m_pairTimer.setInterval(60000);
    connect(&m_pairTimer,&QTimer::timeout,this,[this]{m_pairTimedOut=true;m_pair.kill();});
    connect(&m_pair,&QProcess::stateChanged,this,&Streaming::changed);
    connect(&m_pair,&QProcess::errorOccurred,this,[this](QProcess::ProcessError e){if(e==QProcess::FailedToStart){m_pairTimer.stop();m_pin.clear();fail(QStringLiteral("无法启动配对客户端。"));}});
    connect(&m_pair,qOverload<int,QProcess::ExitStatus>(&QProcess::finished),this,[this](int code,QProcess::ExitStatus exit){
        m_pairTimer.stop();m_pin.clear();
        if(m_pairCancelled) m_status=QStringLiteral("已取消配对");
        else if(code==0&&exit==QProcess::NormalExit){
            for(auto &h:m_hosts) if(h.value("id").toString()==m_pairId)h["paired"]=true;
            if(save())m_status=QStringLiteral("配对成功，可以开始串流");
        }else fail(m_pairTimedOut?QStringLiteral("配对超时，请在 Sunshine 输入屏幕上的 PIN。"):QStringLiteral("配对失败，请检查主机连接并重试。"));
        emit changed();
    });
    m_apps.setStandardInputFile(QProcess::nullDevice());
    m_apps.setStandardErrorFile(QProcess::nullDevice());
    m_appsTimer.setSingleShot(true); m_appsTimer.setInterval(45000);
    connect(&m_appsTimer,&QTimer::timeout,this,[this]{m_appsTimedOut=true;m_apps.kill();});
    connect(&m_apps,&QProcess::stateChanged,this,&Streaming::changed);
    connect(&m_apps,&QProcess::readyReadStandardOutput,this,[this]{
        m_appsOutput+=m_apps.readAllStandardOutput();
        if(m_appsOutput.size()>32768){m_appsOverflow=true;m_apps.kill();}
    });
    connect(&m_apps,&QProcess::errorOccurred,this,[this](QProcess::ProcessError error){
        if(error==QProcess::FailedToStart){m_appsTimer.stop();fail(QStringLiteral("无法读取应用列表，可手动输入应用名称。"));}
    });
    connect(&m_apps,qOverload<int,QProcess::ExitStatus>(&QProcess::finished),this,[this](int code,QProcess::ExitStatus exit){
        m_appsTimer.stop();m_appsOutput+=m_apps.readAllStandardOutput();
        QStringList names;
        if(m_appsCancelled){m_status=QStringLiteral("已取消读取");emit changed();}
        else if(m_appsTimedOut||m_appsOverflow||exit!=QProcess::NormalExit||code!=0||!parseApplications(m_appsOutput,&names))
            fail(QStringLiteral("读取应用失败，请检查连接与配对，或手动输入名称。"));
        else{m_applicationNames=names;m_error.clear();m_status=names.isEmpty()?QStringLiteral("主机没有返回应用，可手动输入名称。"):QStringLiteral("已读取 %1 个应用").arg(names.size());emit changed();emit applicationsReady();}
        m_appsOutput.clear();
    });
}
Streaming::~Streaming(){
    m_pair.disconnect(this);m_apps.disconnect(this);m_pairTimer.stop();m_appsTimer.stop();
    if(m_reply)m_reply->disconnect(this);
    for(auto *process:{&m_pair,&m_apps})if(process->state()!=QProcess::NotRunning){process->kill();process->waitForFinished(1500);}
}
void Streaming::configureClient(QString path,QString hash){m_client=std::move(path);m_hash=std::move(hash);emit changed();}
QVariantList Streaming::hosts() const {QVariantList list;for(const auto &h:m_hosts){auto v=h.toVariantMap();v["status"]=m_online.value(h.value("id").toString(),QStringLiteral("未检测"));list.append(v);}return list;}
QVariantMap Streaming::current() const {return m_selected>=0&&m_selected<m_hosts.size()?hosts()[m_selected].toMap():QVariantMap{};}
QString Streaming::validAddress(const QString &value){
    const auto s=value.trimmed(); QHostAddress ip;
    if(ip.setAddress(s))return ip.protocol()==QAbstractSocket::IPv4Protocol?ip.toString():QString();
    if(s.size()>253||!QRegularExpression("^[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$").match(s).hasMatch())return {};
    for(const auto &label:s.split('.'))if(label.isEmpty()||label.size()>63||label.startsWith('-')||label.endsWith('-'))return {};
    return s.toLower();
}
bool Streaming::fail(const QString &message){m_error=message;m_status.clear();emit changed();return false;}
bool Streaming::writeJson(const QString &name,const QJsonObject &data){
    if(!QDir().mkpath(m_directory))return fail(QStringLiteral("无法保存串流设置。"));
    struct stat st{};const auto path=QFile::encodeName(m_directory);
    if(::lstat(path.constData(),&st)!=0||!S_ISDIR(st.st_mode)||st.st_uid!=geteuid()||::chmod(path.constData(),0700)!=0)return fail(QStringLiteral("串流设置目录不可用。"));
    const auto target=m_directory+"/"+name;
    if(!privateFile(target,true))return fail(QStringLiteral("串流设置文件不可用，原文件已保留。"));
    QSaveFile f(target);const auto bytes=QJsonDocument(data).toJson();
    if(!f.open(QIODevice::WriteOnly))return fail(QStringLiteral("无法保存串流设置。"));
    f.setPermissions(QFile::ReadOwner|QFile::WriteOwner);
    if(f.write(bytes)!=bytes.size()||!f.commit())return fail(QStringLiteral("保存失败，当前修改仍保留。"));
    return true;
}
bool Streaming::save(){if(m_loadFailed)return false;QJsonArray a;for(const auto &h:m_hosts)a.append(h);bool ok=writeJson("hosts.json",{{"version",1},{"hosts",a},{"selected",m_hosts.isEmpty()?QString():m_hosts[m_selected].value("id").toString()}});if(ok)m_error.clear();emit changed();return ok;}
bool Streaming::addHost(const QString &input){
    if(busy()||m_loadFailed)return false;const auto address=validAddress(input);
    if(address.isEmpty())return fail(QStringLiteral("请输入有效的 IPv4 地址或主机名。"));
    for(int i=0;i<m_hosts.size();++i)if(m_hosts[i].value("address").toString()==address){if(m_selected!=i)m_applicationNames.clear();m_selected=i;bool ok=save();if(ok)refresh();return ok;}
    if(m_hosts.size()>=32)return fail(QStringLiteral("主机列表已满。"));
    m_hosts.append({{"id",QUuid::createUuid().toString(QUuid::WithoutBraces)},{"name",address},{"address",address},{"application","R46H Desktop Test"},{"preset",0},{"overlay",true},{"paired",false}});
    m_selected=m_hosts.size()-1;m_applicationNames.clear();m_status.clear();bool ok=save();if(ok)refresh();return ok;
}
bool Streaming::edit(const QString &key,const QString &value){
    if(busy()||m_loadFailed||m_hosts.isEmpty())return false;auto &h=m_hosts[m_selected];
    if(key=="address"){auto a=validAddress(value);if(a.isEmpty())return fail(QStringLiteral("主机地址无效。"));h[key]=a;h["paired"]=false;m_applicationNames.clear();m_online.remove(h.value("id").toString());}
    else if((key=="name"&&textValue(value,64))||(key=="application"&&textValue(value,128)))h[key]=value;
    else return fail(QStringLiteral("请输入有效名称。"));
    m_status.clear();return save();
}
bool Streaming::removeSelected(){
    if(busy()||m_loadFailed||m_hosts.isEmpty())return false;
    const auto previous=m_hosts;const int selection=m_selected;
    m_hosts.removeAt(m_selected);m_selected=qMax(0,qMin(m_selected,int(m_hosts.size())-1));
    if(!save()){m_hosts=previous;m_selected=selection;emit changed();return false;}
    m_applicationNames.clear();m_status.clear();emit changed();return true;
}
void Streaming::select(int index){if(busy()||m_hosts.isEmpty())return;const int next=qBound(0,index,int(m_hosts.size())-1);if(next!=m_selected)m_applicationNames.clear();m_selected=next;save();refresh();}
bool Streaming::adjustPreset(int direction) {
    if (busy() || m_loadFailed || m_hosts.isEmpty()) return false;
    auto &host = m_hosts[m_selected];
    host["preset"] = qBound(0, host.value("preset").toInt() + qBound(-2, direction, 2), 2);
    return save();
}
void Streaming::toggleOverlay(){if(busy()||m_hosts.isEmpty())return;auto &h=m_hosts[m_selected];h["overlay"]=!h.value("overlay").toBool();save();}
void Streaming::refresh(){
    if(m_hosts.isEmpty())return;if(m_reply){m_reply->disconnect(this);m_reply->abort();m_reply->deleteLater();}
    const auto h=m_hosts[m_selected];const auto id=h.value("id").toString();m_online[id]=QStringLiteral("检测中");emit changed();
    QUrl url;url.setScheme("http");url.setHost(h.value("address").toString());url.setPort(47989);url.setPath("/serverinfo");url.setQuery("uniqueid=0123456789ABCDEF");
    QNetworkRequest request(url);request.setTransferTimeout(3000);request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);
    auto *reply=m_network.get(request);m_reply=reply;
    connect(reply,&QNetworkReply::readyRead,this,[reply]{if(reply->bytesAvailable()>65536)reply->abort();});
    connect(reply,&QNetworkReply::finished,this,[this,reply,id]{
        bool valid=false;QString hostname;
        if(reply->error()==QNetworkReply::NoError&&reply->bytesAvailable()<=65536){QXmlStreamReader xml(reply->readAll());
            while(!xml.atEnd()){xml.readNext();if(xml.isStartElement()&&xml.name()==QStringLiteral("root"))valid=xml.attributes().value("status_code")==QStringLiteral("200");if(xml.isStartElement()&&xml.name()==QStringLiteral("hostname"))hostname=xml.readElementText();}valid=valid&&!xml.hasError();}
        m_online[id]=valid?QStringLiteral("在线"):QStringLiteral("离线");
        if(valid&&textValue(hostname,64))for(auto &h:m_hosts)if(h.value("id").toString()==id&&h.value("name")==h.value("address")){h["name"]=hostname;save();break;}
        if(m_reply==reply)m_reply.clear();reply->deleteLater();emit changed();
    });
}
bool Streaming::checkClient(){QFile f(m_client);if(!QDir::isAbsolutePath(m_client)||!QFileInfo(m_client).isExecutable()||!QRegularExpression("^[0-9a-f]{64}$").match(m_hash).hasMatch()||!f.open(QIODevice::ReadOnly))return fail(QStringLiteral("串流客户端尚未准备好。"));QCryptographicHash h(QCryptographicHash::Sha256);if(!h.addData(&f)||QString::fromLatin1(h.result().toHex())!=m_hash)return fail(QStringLiteral("串流客户端校验失败。"));return true;}
QProcessEnvironment Streaming::clientEnvironment(bool pairing) const {
    auto e=QProcessEnvironment::systemEnvironment();e.insert("XDG_CONFIG_HOME",m_directory+"/client/config");e.insert("XDG_DATA_HOME",m_directory+"/client/data");e.insert("XDG_CACHE_HOME",m_directory+"/client/cache");
    e.remove("QT_IM_MODULE");e.remove("R46H_VIRTUAL_KEYBOARD");e.insert("SDL_NO_SIGNAL_HANDLERS","1");
    if(pairing){e.insert("QT_QPA_PLATFORM","offscreen");e.insert("QT_QUICK_BACKEND","software");e.insert("SDL_VIDEODRIVER","dummy");}return e;
}
void Streaming::pair(){
    if(busy()||m_hosts.isEmpty()||!save()||!checkClient())return;
    m_pin=QString::number(QRandomGenerator::system()->bounded(10000)).rightJustified(4,'0');m_pairId=m_hosts[m_selected].value("id").toString();m_pairCancelled=m_pairTimedOut=false;m_error.clear();m_status=QStringLiteral("在 Sunshine 中输入此 PIN");
    m_pair.setProcessEnvironment(clientEnvironment(true));m_pair.setWorkingDirectory(m_directory);m_pair.start(m_client,{"pair",m_hosts[m_selected].value("address").toString(),"--pin",m_pin});m_pairTimer.start();emit changed();
}
void Streaming::cancelPair(){
    if(m_apps.state()!=QProcess::NotRunning){m_appsCancelled=true;m_apps.kill();}
    if(m_pair.state()!=QProcess::NotRunning){m_pairCancelled=true;m_pin.clear();m_pair.kill();}
    emit changed();
}
bool Streaming::parseApplications(const QByteArray &output,QStringList *names){
    if(output.size()>32768)return false;
    QStringDecoder decoder(QStringDecoder::Utf8);const QString text=decoder.decode(output);
    if(decoder.hasError())return false;
    QStringList result;
    for(const auto &name:text.split('\n')){
        if(name.isEmpty())continue;
        if(!textValue(name,128)||result.size()>=256||result.contains(name))return false;
        result.append(name);
    }
    *names=result;return true;
}
void Streaming::refreshApplications(){
    if(busy()||m_hosts.isEmpty()||!save()||!checkClient())return;
    m_appsCancelled=m_appsTimedOut=m_appsOverflow=false;m_appsOutput.clear();m_error.clear();
    m_status=QStringLiteral("正在读取应用列表…");
    // Upstream's non-verbose list command writes one application name per stdout line.
    // Keep all stderr private; no raw client output is captured in diagnostics.
    m_apps.setProcessEnvironment(clientEnvironment(true));m_apps.setWorkingDirectory(m_directory);
    m_apps.start(m_client,{"list",m_hosts[m_selected].value("address").toString()});
    m_appsTimer.start();emit changed();
}
bool Streaming::chooseApplication(int index){
    if(index<0||index>=m_applicationNames.size())return false;
    return edit("application",m_applicationNames[index]);
}
QStringList Streaming::streamArguments(const QJsonObject &h){
    if(!validHost(h))return {};int preset=h.value("preset").toInt();
    QStringList a{"stream",h.value("address").toString(),h.value("application").toString(),"--resolution",preset==2?"1024x768":"640x480","--fps",preset==1?"30":"60","--bitrate",preset==2?"8000":preset==1?"3000":"4000","--video-codec","H.264","--video-decoder","hardware","--audio-config","stereo","--no-game-optimization","--no-hdr","--no-yuv444","--no-quit-after"};
    if(h.value("overlay").toBool())a<<"--performance-overlay";return a;
}
bool Streaming::requestStream(){if(busy()||m_hosts.isEmpty()||!save()||!checkClient())return false;
    if(!writeJson("request.json",{{"version",1},{"host",m_hosts[m_selected]}}))return false;m_status.clear();emit launchRequested();return true;}
void Streaming::streamFinished(int exitCode) {
    setStatisticsActive(false);
    // An explicit group stop can terminate the worker before it records a result.
    if (!writeJson("result.json", {{"version", 1}, {"host", current().value("id").toString()}, {"exit", exitCode}})) return;
    m_status=exitCode==0 ? QStringLiteral("串流已结束") : QStringLiteral("上次连接未正常结束，可重新连接");
    emit changed();
}
void Streaming::setStatisticsActive(bool active) {
    m_statisticsExpiry.stop(); m_statisticsPending.clear();
    m_statistics = {{"active", active}, {"available", false}};
    emit statisticsChanged();
}
void Streaming::ingestStatistics(const QByteArray &data) {
    if (!m_statistics.value("active").toBool()) return;
    if (data.size() + m_statisticsPending.size() > 8192) { m_statisticsPending.clear(); return; }
    m_statisticsPending += data;
    while (m_statisticsPending.contains('\n')) {
        const int end = m_statisticsPending.indexOf('\n');
        const auto value = StreamStats::parse(m_statisticsPending.left(end));
        m_statisticsPending.remove(0, end + 1);
        if (value.isEmpty()) continue;
        m_statistics = value.toVariantMap(); m_statistics.remove("version");
        m_statistics.insert("active", true); m_statistics.insert("available", true);
        m_statisticsExpiry.start(); emit statisticsChanged();
    }
}
int Streaming::runPending(int timeoutSeconds){
    if(!checkClient())return 2;QFile request(m_directory+"/request.json");struct stat st{};
    if(::lstat(QFile::encodeName(request.fileName()).constData(),&st)!=0||!S_ISREG(st.st_mode)||st.st_uid!=geteuid()||(st.st_mode&077)!=0||st.st_size>8192||!request.open(QIODevice::ReadOnly))return 2;
    const auto d=QJsonDocument::fromJson(request.readAll()).object();request.close();
    const auto host=d.value("host").toObject();const auto arguments=streamArguments(host);if(d.value("version")!=QJsonValue(1)||arguments.isEmpty())return 2;
    const bool forwardStats = qEnvironmentVariable("R46H_STREAM_STATS") == "1" && StreamStats::preparePipe();
    auto environment = clientEnvironment(false);
    environment.insert("R46H_STREAM_STATS", forwardStats ? "1" : "0");
    if(!request.remove())return 2;QProcess process;process.setProcessEnvironment(environment);process.setWorkingDirectory(m_directory);process.setStandardInputFile(QProcess::nullDevice());
    QFile log(m_directory+"/stream.log");if(!privateFile(log.fileName(),true)||!log.open(QIODevice::WriteOnly|QIODevice::Truncate))return 2;log.setPermissions(QFile::ReadOwner|QFile::WriteOwner);
    QByteArray outputPending, errorPending; qint64 written=0;
    auto consume=[&](QByteArray &pending, const QByteArray &data, bool standardOutput){pending+=data;if(pending.size()>65536){pending.clear();return;}while(pending.contains('\n')){auto line=pending.left(pending.indexOf('\n'));pending.remove(0,line.size()+1);
        if(line.startsWith("R46H_STATS ")) { const auto value=StreamStats::parse(line); if(forwardStats&&standardOutput&&!value.isEmpty())StreamStats::send(StreamStats::encode(value)); continue; }
        const auto lower=line.toLower();if(lower.contains("http")||lower.contains("uniqueid")||lower.contains("credential")||lower.contains("certificate")||lower.contains("key")||lower.contains("pin")||lower.contains("challenge")||lower.contains("salt"))continue;
        if(!(lower.contains("fps")||lower.contains("decoder")||lower.contains("hantro")||lower.contains("v4l2")||lower.contains("reference frames")||lower.contains("rendering time")||lower.contains("network dropped")))continue;
        if(written+line.size()+1<=262144){log.write(line+'\n');written+=line.size()+1;}}};
    auto drainOutput=[&]{consume(outputPending,process.readAllStandardOutput(),true);};
    auto drainError=[&]{consume(errorPending,process.readAllStandardError(),false);};
    connect(&process,&QProcess::readyReadStandardOutput,this,drainOutput);
    connect(&process,&QProcess::readyReadStandardError,this,drainError);
    process.start(m_client,arguments);int result=1;
    if(process.waitForStarted(5000)){if(process.waitForFinished(timeoutSeconds*1000))result=process.exitStatus()==QProcess::NormalExit?process.exitCode():1;else{process.terminate();if(!process.waitForFinished(3000)){process.kill();process.waitForFinished(2000);}result=124;}}
    drainOutput();drainError();if(!writeJson("result.json",{{"version",1},{"host",host.value("id")},{"exit",result}}))return 2;return result;
}
