import React from 'react';

const TsqlConnectionForm = ({
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
  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#0b0f14', color: 'white' }}>
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
        <div style={{ width: '100%', maxWidth: '700px', display: 'flex', flexDirection: 'column', gap: '18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <h1 style={{ margin: 0, fontSize: '24px', fontWeight: 800 }}>MS SQL Connection</h1>
              <p style={{ margin: '6px 0 0', color: '#9ca3af' }}>Provide connection details for Microsoft SQL Server</p>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={onBack}
                style={{ padding: '10px 14px', background: '#111827', color: '#e5e7eb', border: '1px solid #374151', borderRadius: '10px', cursor: 'pointer' }}
              >
                Back
              </button>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', background: '#0f172a', border: '1px solid #1f2937', borderRadius: '12px', padding: '16px' }}>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={{ display: 'block', fontSize: '12px', color: '#9ca3af', marginBottom: '6px' }}>Driver</label>
              <select
                value={connectionDetails.driver}
                onChange={(e) => setConnectionDetails({ ...connectionDetails, driver: e.target.value })}
                style={{ width: '100%', padding: '10px 12px', background: '#111827', color: '#e5e7eb', border: '1px solid #374151', borderRadius: '10px' }}
              >
                <option value="ODBC Driver 18 for SQL Server">ODBC Driver 18 for SQL Server</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '12px', color: '#9ca3af', marginBottom: '6px' }}>Server</label>
              <input
                type="text"
                value={connectionDetails.server}
                onChange={(e) => setConnectionDetails({ ...connectionDetails, server: e.target.value })}
                placeholder="host,host:port or host\\instance"
                style={{ width: '100%', padding: '10px 12px', background: '#111827', color: '#e5e7eb', border: '1px solid #374151', borderRadius: '10px' }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '12px', color: '#9ca3af', marginBottom: '6px' }}>Database</label>
              <input
                type="text"
                value={connectionDetails.database}
                onChange={(e) => setConnectionDetails({ ...connectionDetails, database: e.target.value })}
                placeholder="Database name"
                style={{ width: '100%', padding: '10px 12px', background: '#111827', color: '#e5e7eb', border: '1px solid #374151', borderRadius: '10px' }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '12px', color: '#9ca3af', marginBottom: '6px' }}>Username</label>
              <input
                type="text"
                value={connectionDetails.username}
                onChange={(e) => setConnectionDetails({ ...connectionDetails, username: e.target.value })}
                placeholder="User"
                style={{ width: '100%', padding: '10px 12px', background: '#111827', color: '#e5e7eb', border: '1px solid #374151', borderRadius: '10px' }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '12px', color: '#9ca3af', marginBottom: '6px' }}>Password</label>
              <input
                type="password"
                value={connectionDetails.password}
                onChange={(e) => setConnectionDetails({ ...connectionDetails, password: e.target.value })}
                placeholder="Password"
                style={{ width: '100%', padding: '10px 12px', background: '#111827', color: '#e5e7eb', border: '1px solid #374151', borderRadius: '10px' }}
              />
            </div>
          </div>

          {metadataFetched ? (
            <div style={{
              padding: '12px 14px',
              borderRadius: '10px',
              background: 'rgba(16, 185, 129, 0.12)',
              border: '1px solid rgba(16, 185, 129, 0.35)',
              color: '#bbf7d0',
              fontSize: '13px',
              fontWeight: 600,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <span>Metadata fetched successfully. Click Continue to analyze the database.</span>
            </div>
          ) : null}

          {/* OpenAI Toggle Section */}
          <div style={{ padding: '20px', background: '#111827', border: '1px solid #374151', borderRadius: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
              <input
                type="checkbox"
                id="useOpenAI"
                checked={useOpenAI || false}
                onChange={(e) => setUseOpenAI(e.target.checked)}
                style={{ width: '18px', height: '18px', cursor: 'pointer' }}
              />
              <label htmlFor="useOpenAI" style={{ fontSize: '16px', fontWeight: 600, cursor: 'pointer' }}>
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
                    fontSize: '14px'
                  }}
                />
                <p style={{ margin: 0, fontSize: '13px', color: '#9ca3af', lineHeight: '1.5' }}>
                  OpenAI key will be used for LLM-powered lineage analysis. The key is not stored and is only passed to the analyzer.
                </p>
              </div>
            ) : (
              <div style={{ padding: '12px', background: '#0b0f14', border: '1px solid #374151', borderRadius: '8px' }}>
                <p style={{ margin: 0, fontSize: '13px', color: '#9ca3af', lineHeight: '1.5' }}>
                  OpenAI key is not selected. The app will default to usage of Ollama. Make sure Ollama is running on <strong>http://localhost:11434</strong> and the <strong>qwen2.5-coder:14b</strong> model is pulled.
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
              style={{ padding: '10px 16px', background: isSubmitting ? '#1f2937' : '#2563eb', color: 'white', border: '1px solid #1d4ed8', borderRadius: '10px', cursor: isSubmitting ? 'not-allowed' : 'pointer', opacity: isSubmitting ? 0.7 : 1 }}
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

export default TsqlConnectionForm;


