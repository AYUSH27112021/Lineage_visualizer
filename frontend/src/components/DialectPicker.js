import React from 'react';

const DialectPicker = ({ options, onBack, onSelect, useOpenAI, setUseOpenAI, openAIKey, setOpenAIKey }) => {
  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#0b0f14', color: 'white' }}>
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
        <div style={{ maxWidth: '900px', width: '100%', display: 'flex', flexDirection: 'column', gap: '18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <h1 style={{ margin: 0, fontSize: '24px', fontWeight: 800 }}>Select SQL Dialect</h1>
              <p style={{ margin: '6px 0 0', color: '#9ca3af' }}>Choose the SQL dialect to parse your scripts correctly.</p>
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
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
            {options.map(opt => (
              <button
                key={opt.key}
                onClick={() => onSelect(opt)}
                style={{
                  display: 'flex', alignItems: 'center', gap: '12px',
                  padding: '16px', background: '#111827', color: 'white',
                  border: '1px solid #374151', borderRadius: '12px', cursor: 'pointer',
                  textAlign: 'left'
                }}
              >
                <div style={{ width: '44px', height: '44px', borderRadius: '10px', background: '#0b1220', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <img src={opt.img} alt={`${opt.label} logo`} style={{ maxWidth: '36px', maxHeight: '36px', objectFit: 'contain' }} />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  <span style={{ fontWeight: 800, fontSize: '16px' }}>{opt.label}</span>
                  <span style={{ opacity: 0.85, fontSize: '12px', color: '#9ca3af' }}>{opt.sub}</span>
                </div>
              </button>
            ))}
          </div>
          
          {/* OpenAI Toggle Section */}
          <div style={{ marginTop: '24px', padding: '20px', background: '#111827', border: '1px solid #374151', borderRadius: '12px' }}>
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
        </div>
      </div>
    </div>
  );
};

export default DialectPicker;


