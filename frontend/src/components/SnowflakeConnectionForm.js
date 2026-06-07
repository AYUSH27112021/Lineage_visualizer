import React from 'react';

const inputStyle = {
  width: '100%',
  padding: '10px 12px',
  background: '#111827',
  color: '#e5e7eb',
  border: '1px solid #374151',
  borderRadius: '10px'
};

const labelStyle = {
  display: 'block',
  fontSize: '12px',
  color: '#9ca3af',
  marginBottom: '6px'
};

const SnowflakeConnectionForm = ({
  connectionDetails,
  setConnectionDetails,
  onBack,
  onRunAnalysis,
  useOpenAI,
  setUseOpenAI,
  openAIKey,
  setOpenAIKey,
}) => {
  const updateField = (key, value) => {
    setConnectionDetails(prev => ({
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
              <h1 style={{ margin: 0, fontSize: '24px', fontWeight: 800 }}>Snowflake Connection</h1>
              <p style={{ margin: '6px 0 0', color: '#9ca3af' }}>
                Provide connection details for Snowflake metadata-based lineage analysis.
              </p>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={onBack}
                style={{
                  padding: '10px 14px',
                  background: '#111827',
                  color: '#e5e7eb',
                  border: '1px solid #374151',
                  borderRadius: '10px',
                  cursor: 'pointer'
                }}
              >
                Back
              </button>
            </div>
          </div>

          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '16px',
            background: '#0f172a',
            border: '1px solid #1f2937',
            borderRadius: '12px',
            padding: '16px'
          }}>
            <div>
              <label style={labelStyle}>Account</label>
              <input
                type="text"
                value={connectionDetails.account || ''}
                onChange={(e) => updateField('account', e.target.value)}
                placeholder="e.g. XBXMLZX-MIA01615"
                style={inputStyle}
              />
            </div>

            <div>
              <label style={labelStyle}>Database</label>
              <input
                type="text"
                value={connectionDetails.database || ''}
                onChange={(e) => updateField('database', e.target.value)}
                placeholder="SNOWFLAKE_SAMPLE_DATA"
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
              <label style={labelStyle}>Password (optional for externalbrowser)</label>
              <input
                type="password"
                value={connectionDetails.password || ''}
                onChange={(e) => updateField('password', e.target.value)}
                placeholder="Password"
                style={inputStyle}
              />
            </div>

            <div>
              <label style={labelStyle}>Warehouse</label>
              <input
                type="text"
                value={connectionDetails.warehouse || ''}
                onChange={(e) => updateField('warehouse', e.target.value)}
                placeholder="COMPUTE_WH"
                style={inputStyle}
              />
            </div>

            <div>
              <label style={labelStyle}>Role (optional)</label>
              <input
                type="text"
                value={connectionDetails.role || ''}
                onChange={(e) => updateField('role', e.target.value)}
                placeholder="SYSADMIN"
                style={inputStyle}
              />
            </div>

            <div>
              <label style={labelStyle}>Authenticator</label>
              <select
                value={connectionDetails.authenticator || 'externalbrowser'}
                onChange={(e) => updateField('authenticator', e.target.value)}
                style={{ ...inputStyle, background: '#0f172a' }}
              >
                <option value="externalbrowser">externalbrowser (SSO)</option>
                <option value="snowflake">snowflake (username/password)</option>
                <option value="oauth">oauth</option>
              </select>
            </div>

          </div>

          <div style={{
            padding: '16px',
            borderRadius: '10px',
            background: '#0f172a',
            border: '1px solid #1f2937',
            color: '#9ca3af',
            fontSize: '13px',
            lineHeight: 1.6
          }}>
            <strong style={{ color: 'white' }}>Tip:</strong> When using <code style={{ background: '#111827', padding: '2px 6px', borderRadius: '6px' }}>externalbrowser</code> authentication, the Snowflake connector will open your default browser to complete SSO login.
          </div>

          <div style={{ padding: '20px', background: '#111827', border: '1px solid #374151', borderRadius: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
              <input
                type="checkbox"
                id="snowflakeUseOpenAI"
                checked={useOpenAI || false}
                onChange={(e) => setUseOpenAI(e.target.checked)}
                style={{ width: '18px', height: '18px', cursor: 'pointer' }}
              />
              <label htmlFor="snowflakeUseOpenAI" style={{ fontSize: '16px', fontWeight: 600, cursor: 'pointer' }}>
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
                  The key is not stored and is only forwarded to the analyzer for LLM-powered lineage.
                </p>
              </div>
            ) : (
              <div style={{ padding: '12px', background: '#0b0f14', border: '1px solid #374151', borderRadius: '8px' }}>
                <p style={{ margin: 0, fontSize: '13px', color: '#9ca3af', lineHeight: '1.5' }}>
                  Without an OpenAI key the analyzer will default to Ollama (<strong>qwen2.5-coder:14b</strong>). Ensure Ollama is running on <strong>http://localhost:11434</strong>.
                </p>
              </div>
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <button
              onClick={onBack}
              style={{
                padding: '10px 14px',
                background: '#111827',
                color: '#e5e7eb',
                border: '1px solid #374151',
                borderRadius: '10px',
                cursor: 'pointer'
              }}
            >
              Back
            </button>
            <button
              onClick={onRunAnalysis}
              style={{
                padding: '10px 16px',
                background: '#2563eb',
                color: 'white',
                border: '1px solid #1d4ed8',
                borderRadius: '10px',
                cursor: 'pointer'
              }}
            >
              Run Analysis
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SnowflakeConnectionForm;


