use std::fs::{File, OpenOptions};
use std::path::Path;

use crate::error::{Error, Result};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FileIdentity {
    storage: u64,
    object_high: u64,
    object_low: u64,
    size: u64,
    links: u64,
    reparse: bool,
}

impl FileIdentity {
    pub fn stable_token(&self) -> String {
        format!("{}-{}-{}", self.storage, self.object_high, self.object_low)
    }

    pub fn size(&self) -> u64 {
        self.size
    }

    pub fn links(&self) -> u64 {
        self.links
    }

    pub fn is_reparse_point(&self) -> bool {
        self.reparse
    }
}

pub fn open_existing(path: &Path, writable: bool) -> Result<File> {
    let mut options = OpenOptions::new();
    options.read(true).write(writable);
    configure_no_follow(&mut options);
    options
        .open(path)
        .map_err(|error| Error::io("open existing file without following links", error))
}

#[cfg(unix)]
fn configure_no_follow(options: &mut OpenOptions) {
    use std::os::unix::fs::OpenOptionsExt;
    options.custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC);
}

#[cfg(windows)]
fn configure_no_follow(options: &mut OpenOptions) {
    use std::os::windows::fs::OpenOptionsExt;
    const FILE_FLAG_OPEN_REPARSE_POINT: u32 = 0x0020_0000;
    options.custom_flags(FILE_FLAG_OPEN_REPARSE_POINT);
}

#[cfg(unix)]
pub fn identity(file: &File) -> Result<FileIdentity> {
    use std::os::unix::fs::MetadataExt;
    let metadata = file
        .metadata()
        .map_err(|error| Error::io("inspect opened file identity", error))?;
    Ok(FileIdentity {
        storage: metadata.dev(),
        object_high: 0,
        object_low: metadata.ino(),
        size: metadata.len(),
        links: metadata.nlink(),
        reparse: false,
    })
}

#[cfg(windows)]
pub fn identity(file: &File) -> Result<FileIdentity> {
    use std::ffi::c_void;
    use std::os::windows::io::AsRawHandle;

    #[allow(non_snake_case)]
    #[repr(C)]
    struct FileTime {
        dwLowDateTime: u32,
        dwHighDateTime: u32,
    }

    #[allow(non_snake_case)]
    #[repr(C)]
    struct ByHandleFileInformation {
        dwFileAttributes: u32,
        ftCreationTime: FileTime,
        ftLastAccessTime: FileTime,
        ftLastWriteTime: FileTime,
        dwVolumeSerialNumber: u32,
        nFileSizeHigh: u32,
        nFileSizeLow: u32,
        nNumberOfLinks: u32,
        nFileIndexHigh: u32,
        nFileIndexLow: u32,
    }

    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn GetFileInformationByHandle(
            file: *mut c_void,
            information: *mut ByHandleFileInformation,
        ) -> i32;
    }

    const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x0000_0400;
    let mut information = std::mem::MaybeUninit::<ByHandleFileInformation>::uninit();
    // SAFETY: the handle belongs to a live File and the output points to valid,
    // writable storage for the exact Windows structure.
    let succeeded =
        unsafe { GetFileInformationByHandle(file.as_raw_handle(), information.as_mut_ptr()) };
    if succeeded == 0 {
        return Err(Error::io(
            "inspect Windows file handle identity",
            std::io::Error::last_os_error(),
        ));
    }
    // SAFETY: a nonzero return documents that the structure was initialized.
    let information = unsafe { information.assume_init() };
    Ok(FileIdentity {
        storage: u64::from(information.dwVolumeSerialNumber),
        object_high: u64::from(information.nFileIndexHigh),
        object_low: u64::from(information.nFileIndexLow),
        size: (u64::from(information.nFileSizeHigh) << 32) | u64::from(information.nFileSizeLow),
        links: u64::from(information.nNumberOfLinks),
        reparse: information.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT != 0,
    })
}
