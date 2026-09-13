use std::path::PathBuf;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("invalid argument: {0}")]
    InvalidArgument(String),
    #[error("invalid data: {0}")]
    InvalidData(String),
    #[error("unsafe path: {0}")]
    UnsafePath(PathBuf),
    #[error("unsupported operation: {0}")]
    Unsupported(String),
    #[error("transaction cancelled")]
    Cancelled,
    #[error(
        "partial media write at offset {target_offset} after {bytes_written}/{target_length} bytes: {message}"
    )]
    PartialWrite {
        target_offset: u64,
        target_length: u64,
        bytes_written: u64,
        message: String,
    },
    #[error("I/O error during {context}: {source}")]
    Io {
        context: &'static str,
        #[source]
        source: std::io::Error,
    },
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
}

impl Error {
    pub fn io(context: &'static str, source: std::io::Error) -> Self {
        Self::Io { context, source }
    }
}

pub type Result<T> = std::result::Result<T, Error>;
