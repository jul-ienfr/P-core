use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct LedgerEnvelope<T> {
    pub kind: &'static str,
    pub payload: T,
}

impl<T: Serialize> LedgerEnvelope<T> {
    pub fn to_json(&self) -> Result<String, serde_json::Error> {
        serde_json::to_string(self)
    }
}
