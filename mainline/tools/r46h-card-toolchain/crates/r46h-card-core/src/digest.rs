use std::io::{Read, Seek, SeekFrom};

use sha2::{Digest, Sha256};

use crate::error::{Error, Result};

pub const SHA256_LEN: usize = 64;
const BUFFER_SIZE: usize = 1024 * 1024;

pub fn is_sha256(value: &str) -> bool {
    value.len() == SHA256_LEN
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

pub fn hash_reader<R: Read + ?Sized>(reader: &mut R) -> Result<(String, u64)> {
    let mut hasher = StreamHasher::new();
    let mut buffer = vec![0_u8; BUFFER_SIZE];
    let mut total = 0_u64;
    loop {
        let count = reader
            .read(&mut buffer)
            .map_err(|source| Error::io("read for SHA-256", source))?;
        if count == 0 {
            break;
        }
        hasher.update(&buffer[..count]);
        total = total
            .checked_add(count as u64)
            .ok_or_else(|| Error::InvalidData("hashed byte count overflow".into()))?;
    }
    Ok((hasher.finalize_hex(), total))
}

pub fn hash_range<R: Read + Seek + ?Sized>(
    reader: &mut R,
    offset: u64,
    length: u64,
) -> Result<String> {
    reader
        .seek(SeekFrom::Start(offset))
        .map_err(|source| Error::io("seek for SHA-256", source))?;
    let mut limited = reader.take(length);
    let (digest, bytes) = hash_reader(&mut limited)?;
    if bytes != length {
        return Err(Error::InvalidData(format!(
            "short read while hashing: expected {length} bytes, read {bytes}"
        )));
    }
    Ok(digest)
}

pub(crate) struct StreamHasher(Sha256);

impl StreamHasher {
    pub(crate) fn new() -> Self {
        Self(Sha256::new())
    }

    pub(crate) fn update(&mut self, bytes: &[u8]) {
        self.0.update(bytes);
    }

    pub(crate) fn finalize_hex(self) -> String {
        format!("{:x}", self.0.finalize())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn known_vectors_and_block_boundaries() {
        let vectors = [
            (
                Vec::new(),
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            ),
            (
                b"abc".to_vec(),
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            ),
            (
                vec![b'a'; 55],
                "9f4390f8d30c2dd92ec9f095b65e2b9ae9b0a925a5258e241c9f1e910f734318",
            ),
            (
                vec![b'a'; 56],
                "b35439a4ac6f0948b6d6f9e3c6af0f5f590ce20f1bde7090ef7970686ec6738a",
            ),
            (
                vec![b'a'; 64],
                "ffe054fe7ae0cb6dc65c3af9b61d5209f439851db43d0ba5997337df154668eb",
            ),
            (
                vec![b'a'; 65],
                "635361c48bb9eab14198e76ea8ab7f1a41685d6ad62aa9146d301d4f17eb0ae0",
            ),
        ];
        for (bytes, expected) in vectors {
            let (actual, count) = hash_reader(&mut bytes.as_slice()).unwrap();
            assert_eq!(count, bytes.len() as u64);
            assert_eq!(actual, expected);
        }
    }
}
