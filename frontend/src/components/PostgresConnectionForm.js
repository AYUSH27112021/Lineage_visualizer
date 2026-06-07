import React from 'react';

const inputStyle = {
  width: '100%',
  padding: '10px 12px',
  background: '#111827',
  color: '#e5e7eb',
  border: '1px solid #374151',
  borderRadius: '10px',
};

const labelStyle = {
  display: 'block',
  fontSize: '12px',
  color: '#9ca3af',
  marginBottom: '6px',
};

const PostgresConnectionForm = ({
  connectionDetails,
  setConnectionDetails,
  onBack,
  onFetchMetadata,
  onProceed,
  isSubmitting,
  metadataFetched,
  useOpenAI,
  setUseOpenAI,
  openAIKey,
  setOpenAIKey,
}) => {
  const updateField = (key, value) => {
    setConnectionDetails((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#0b0f14', color: 'white' }}>
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
        <div style={{ width: '100%', maxWidth: '720px', display: 'flex', flexDirection: 'column', gap: '18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <h1 style={{ margin: 0, fontSize: '24px', fontWeight: 800 }}>PostgreSQL Connection</h1>
              <p style={{ margin: '6px 0 0', color: '#9ca3af' }}>
                Connect directly to PostgreSQL to extract metadata and run lineage analysis.
              </p>
            </div>
            <button
              onClick={onBack}
              style={{
                padding: '10px 14px',
                background: '#111827',
                color: '#e5e7eb',
                border: '1px solid #374151',
                borderRadius: '10px',
                cursor: 'pointer',
              }}
            >
              Back
            </button>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '16px',
              background: '#0f172a',
              border: '1px solid #1f2937',
              borderRadius: '12px',
              padding: '16px',
            }}
          >
            <div>
              <label style={labelStyle}>Host</label>
              <input
                type="text"
                value={connectionDetails.host || ''}
                onChange={(e) => updateField('host', e.target.value)}
                placeholder="e.g. postgres.company.com"
                style={inputStyle}
              />
            </div>

            <div>
              <label style={labelStyle}>Port</label>
              <input
                type="number"
                value={connectionDetails.port || '5432'}
                onChange={(e) => updateField('port', e.target.value)}
                placeholder="5432"
                style={inputStyle}
              />
            </div>

            <div>
              <label style={labelStyle}>Database</label>
              <input
                type="text"
                value={connectionDetails.database || ''}
                onChange={(e) => updateField('database', e.target.value)}
                placeholder="Database name"
                style={inputStyle}
              />
            </div>

            <div>
              <label style={labelStyle}>Username</label>
              <input
                type="text"
                value={connectionDetails.username || ''}
                onChange={(e) => updateField('username', e.target.value)}
                placeholder="User"
                style={inputStyle}
              />
            </div>

            <div>
              <label style={labelStyle}>Password</label>
              <input
                type="password"
                value={connectionDetails.password || ''}
                onChange={(e) => updateField('password', e.target.value)}
                placeholder="Password"
                style={inputStyle}
              />
            </div>
          </div>

          {metadataFetched ? (
            <div
              style={{
                padding: '12px 14px',
                borderRadius: '10px',
                background: 'rgba(16, 185, 129, 0.12)',
                border: '1px solid rgba(16, 185, 129, 0.35)',
                color: '#bbf7d0',
                fontSize: '13px',
                fontWeight: 600,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <span>Metadata cached successfully. Continue to run the analyzer.</span>
            </div>
          ) : null}

          <div style={{ padding: '20px', background: '#111827', border: '1px solid #374151', borderRadius: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
              <input
                type="checkbox"
                id="postgresUseOpenAI"
                checked={useOpenAI || false}
                onChange={(e) => setUseOpenAI(e.target.checked)}
                style={{ width: '18px', height: '18px', cursor: 'pointer' }}
              />
              <label htmlFor="postgresUseOpenAI" style={{ fontSize: '16px', fontWeight: 600, cursor: 'pointer' }}>
                Use OpenAI Key
              </label>
            </div>

            {useOpenAI ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <input
                  type="password"
                  placeholder="Enter your OpenAI API key"
                  value={openAIKey || ''}
                  onChange={(e) => setOpenAIKey(e.target.value)}
                  style={{
                    padding: '12px',
                    background: '#0b0f14',
                    border: '1px solid #374151',
                    borderRadius: '8px',
                    color: 'white',
                    fontSize: '14px',
                  }}
                />
                <p style={{ margin: 0, fontSize: '13px', color: '#9ca3af', lineHeight: '1.5' }}>
                  Your key is forwarded only to the backend analyzer and never stored.
                </p>
              </div>
            ) : (
              <div style={{ padding: '12px', background: '#0b0f14', border: '1px solid #374151', borderRadius: '8px' }}>
                <p style={{ margin: 0, fontSize: '13px', color: '#9ca3af', lineHeight: '1.5' }}>
                  Without an OpenAI key the analyzer defaults to Ollama (<strong>qwen2.5-coder:14b</strong>).
                </p>
              </div>
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <button
              onClick={onBack}
              style={{ padding: '10px 14px', background: '#111827', color: '#e5e7eb', border: '1px solid #374151', borderRadius: '10px', cursor: 'pointer' }}
            >
              Back
            </button>
            <button
              onClick={onFetchMetadata}
              disabled={isSubmitting}
              style={{
                padding: '10px 16px',
                background: isSubmitting ? '#1f2937' : '#2563eb',
                color: 'white',
                border: '1px solid #1d4ed8',
                borderRadius: '10px',
                cursor: isSubmitting ? 'not-allowed' : 'pointer',
                opacity: isSubmitting ? 0.7 : 1,
              }}
            >
              {isSubmitting ? 'Fetching…' : metadataFetched ? 'Refetch Metadata' : 'Fetch Metadata'}
            </button>
            {metadataFetched ? (
              <button
                onClick={onProceed}
                style={{ padding: '10px 16px', background: '#10b981', color: 'white', border: '1px solid #047857', borderRadius: '10px', cursor: 'pointer' }}
              >
                Continue
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
};

export default PostgresConnectionForm;


