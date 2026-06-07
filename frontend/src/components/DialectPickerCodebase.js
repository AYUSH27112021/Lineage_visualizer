import React from 'react';

const DialectPickerCodebase = ({ onBack, onSelect }) => {
  const options = [
    { key: 'tsql', label: 'Microsoft SQL Server', sub: 'T-SQL', img: 'https://cdn.jsdelivr.net/npm/simple-icons@v11/icons/microsoftsqlserver.svg' },
    { key: 'snowflake', label: 'Snowflake Data Cloud', sub: 'Snowflake SQL', img: 'https://upload.wikimedia.org/wikipedia/commons/f/ff/Snowflake_Logo.svg' },
    { key: 'teradata', label: 'Teradata Vantage', sub: 'Teradata SQL', img: 'https://upload.wikimedia.org/wikipedia/commons/c/cd/Teradata_logo_2018.svg' },
    { key: 'oracle', label: 'Oracle Database', sub: 'Oracle PL/SQL', img: 'https://upload.wikimedia.org/wikipedia/commons/5/50/Oracle_logo.svg' },
    { key: 'postgres', label: 'PostgreSQL', sub: 'PostgreSQL SQL', img: 'https://upload.wikimedia.org/wikipedia/commons/2/29/Postgresql_elephant.svg' },
    { key: 'mysql', label: 'MySQL / MariaDB', sub: 'MySQL SQL', img: 'https://upload.wikimedia.org/wikipedia/en/d/dd/MySQL_logo.svg' },
    { key: 'mariadb', label: 'MariaDB', sub: 'MariaDB', img: 'https://upload.wikimedia.org/wikipedia/commons/c/c9/MariaDB_Logo.svg' },
    { key: 'sqlite', label: 'SQLite', sub: 'SQLite SQL', img: 'https://upload.wikimedia.org/wikipedia/commons/3/38/SQLite370.svg' },
  ];

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#0b0f14', color: 'white' }}>
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
        <div style={{ maxWidth: '900px', width: '100%', display: 'flex', flexDirection: 'column', gap: '18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <h1 style={{ margin: 0, fontSize: '24px', fontWeight: 800 }}>Select Dialect for Codebase Scan</h1>
              <p style={{ margin: '6px 0 0', color: '#9ca3af' }}>Choose the SQL dialect to scan your codebase.</p>
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
        </div>
      </div>
    </div>
  );
};

export default DialectPickerCodebase;


