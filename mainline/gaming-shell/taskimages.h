#pragma once
#include "applications.h"
#include <QPointer>
#include <QQuickImageProvider>

// Local, synchronous, memory-only images. The remote control protocol never
// exports these images; the entire task page is a sensitive surface.
class TaskImages final : public QQuickImageProvider {
    QPointer<Applications> applications;
public:
    explicit TaskImages(Applications *value):QQuickImageProvider(QQuickImageProvider::Image),applications(value){}
    QImage requestImage(const QString &id,QSize *size,const QSize &) override {
        const auto image=applications?applications->thumbnail(id.section('/',0,0)):QImage();
        if(size)*size=image.size();
        return image;
    }
};
