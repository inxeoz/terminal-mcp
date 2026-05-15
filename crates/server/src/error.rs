use std::fmt;

#[derive(Debug)]
pub enum Error {
    NotFound(String),
    AlreadyExists(String),
    Internal(anyhow::Error),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::NotFound(msg) => write!(f, "not found: {msg}"),
            Error::AlreadyExists(msg) => write!(f, "already exists: {msg}"),
            Error::Internal(e) => write!(f, "internal error: {e}"),
        }
    }
}

impl std::error::Error for Error {}

impl From<anyhow::Error> for Error {
    fn from(e: anyhow::Error) -> Self {
        Error::Internal(e)
    }
}

impl From<sqlx::Error> for Error {
    fn from(e: sqlx::Error) -> Self {
        Error::Internal(anyhow::anyhow!(e))
    }
}

pub type Result<T> = std::result::Result<T, Error>;
