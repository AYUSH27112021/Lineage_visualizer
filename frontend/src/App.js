import React, { useState, useRef, useEffect } from 'react';
import { 
  ZoomIn, 
  ZoomOut, 
  Maximize2, 
  Database, 
  File, 
  ChevronDown, 
  ChevronRight,
  ChevronLeft,
  AlertCircle,
  CheckCircle,
  Sun,
  Moon,
  Link2,
  Eye,
  Download,
  Info,
  X,
  Loader2
} from 'lucide-react';
import dagre from 'dagre';
import './App.css';
import DialectPicker from './components/DialectPicker';
import DialectPickerCodebase from './components/DialectPickerCodebase';
import TsqlConnectionForm from './components/TsqlConnectionForm';
import SnowflakeConnectionForm from './components/SnowflakeConnectionForm';
import TeradataConnectionForm from './components/TeradataConnectionForm';
import PostgresConnectionForm from './components/PostgresConnectionForm';
import OracleConnectionForm from './components/OracleConnectionForm';

const SQLLineageViz = () => {
  const [lineageReport, setLineageReport] = useState(null);
  const [lineageData, setLineageData] = useState(null);
  const [zoom, setZoom] = useState(0.8);
  const [pan, setPan] = useState({ x: 200, y: 100 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [showStart, setShowStart] = useState(true);
  
  const [hoveredConnections, setHoveredConnections] = useState([]); // all connections related to hovered column
  const [expandedTables, setExpandedTables] = useState(new Set());
  const [parseErrors] = useState([]);
  const [hiddenPreviousLevels, setHiddenPreviousLevels] = useState(new Set());
  const [hiddenNextLevels, setHiddenNextLevels] = useState(new Set());
  const tablePositionsRef = useRef(new Map()); // Store stable positions in ref
  const canvasRef = useRef(null);
  const [theme, setTheme] = useState('dark');
  const [showAllColumnConnections, setShowAllColumnConnections] = useState(false);
  const [autoExpandedOnShowAll, setAutoExpandedOnShowAll] = useState(new Set());
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [previewSVG, setPreviewSVG] = useState('');
  const [showTablesSection, setShowTablesSection] = useState(true);
  const [showProceduresSection, setShowProceduresSection] = useState(false);
  const [procedureLineage, setProcedureLineage] = useState(null);
  const [procedureLineageData, setProcedureLineageData] = useState(null);
  const [procedureSearch, setProcedureSearch] = useState('');
  const [selectedProcedure, setSelectedProcedure] = useState(null);
  const [isRightPanelOpen, setIsRightPanelOpen] = useState(true); // Panel open by default
  const [expandedProcedures, setExpandedProcedures] = useState(new Set());
  const [hoveredProcConnections, setHoveredProcConnections] = useState([]);
  const [summaryReport, setSummaryReport] = useState(null);
  const [showDialectPicker, setShowDialectPicker] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);
  const [selectedDialect, setSelectedDialect] = useState('tsql');
  const [showConnectionForm, setShowConnectionForm] = useState(false);
  const [connectionDetails, setConnectionDetails] = useState({
    server: '',
    host: '',
    database: '',
    username: '',
    password: '',
    driver: 'ODBC Driver 18 for SQL Server',
    account: '',
    warehouse: '',
    role: '',
    authenticator: 'externalbrowser',
    logmech: 'TD2',
    encryptdata: true,
    charset: 'UTF8',
    tmode: 'ANSI',
    port: '',
    serviceName: '',
    targetSchemas: '',
  });
  const [showTableDetailsSection, setShowTableDetailsSection] = useState(false);
  const [focusedTable, setFocusedTable] = useState(null);
  const [focusedTableConnections, setFocusedTableConnections] = useState(new Set());
  const folderInputRef = useRef(null);
  const [tableSearch, setTableSearch] = useState('');
  const [isConnectionSubmitting, setIsConnectionSubmitting] = useState(false);
  const [metadataFilePath, setMetadataFilePath] = useState(null);
  const [metadataFetched, setMetadataFetched] = useState(false);
  const [toast, setToast] = useState(null);
  const toastTimeoutRef = useRef(null);
  const panelSpaceTimeoutRef = useRef(null);
  const [scriptSelectionMode, setScriptSelectionMode] = useState('folder');
  const [useEnhancedFlow, setUseEnhancedFlow] = useState(false);
  const [useOpenAI, setUseOpenAI] = useState(false);
  const [openAIKey, setOpenAIKey] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [showLLMInfo, setShowLLMInfo] = useState(false);
  const [selectedLLMInfo] = useState(null);
  const [analysisError, setAnalysisError] = useState(null);
  const [lineageNotice, setLineageNotice] = useState(null);
  const [shouldReserveRightPanelSpace, setShouldReserveRightPanelSpace] = useState(false);

  const RIGHT_PANEL_WIDTH = 400;
  const PANEL_TRANSITION_DURATION = 350;
  const isProcedurePanelActive = Boolean(selectedProcedure && showProceduresSection);

  useEffect(() => {
    return () => {
      if (toastTimeoutRef.current) {
        clearTimeout(toastTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (lineageData || procedureLineageData || summaryReport) {
      setShowStart(false);
      setShowConnectionForm(false);
      setShowDialectPicker(false);
    }
  }, [lineageData, procedureLineageData, summaryReport]);

  useEffect(() => {
    setMetadataFetched(false);
    setMetadataFilePath(null);
  }, [selectedDialect]);

  useEffect(() => {
    if (showStart) {
      setLineageNotice(null);
    }
  }, [showStart]);

  const updateLineageNotice = (statementReportArg, procedureReportArg, convertedDataArg, { isMetadata } = {}) => {
    const viewCount = statementReportArg?.views?.length || 0;
    const queryCount = statementReportArg?.query_history?.length || 0;
    const procedureCount = Object.keys(procedureReportArg?.procedures || {}).length;
    const functionCount = Object.keys(procedureReportArg?.functions || {}).length;
    const hasStatements = (viewCount + queryCount) > 0;
    const hasProcedures = (procedureCount + functionCount) > 0;
    if (!hasStatements && !hasProcedures) {
      const message = isMetadata
        ? 'No SQL or lineage statements were found in the extracted metadata. Only base table metadata is available for visualization.'
        : 'No SQL statements produced lineage results. Please provide scripts that include queries, views, or procedures.';
      setLineageNotice(message);
    } else {
      setLineageNotice(null);
    }
  };

  const showToast = (title, message = '', type = 'info') => {
    if (toastTimeoutRef.current) {
      clearTimeout(toastTimeoutRef.current);
    }
    setToast({ title, message, type });
    toastTimeoutRef.current = setTimeout(() => {
      setToast(null);
      toastTimeoutRef.current = null;
    }, 4500);
  };

  const renderToast = () => {
    if (!toast) return null;

    const palettes = {
      success: {
        background: 'rgba(16, 185, 129, 0.15)',
        border: '1px solid rgba(16, 185, 129, 0.35)',
        color: '#ecfdf5',
        iconColor: '#34d399',
      },
      error: {
        background: 'rgba(239, 68, 68, 0.15)',
        border: '1px solid rgba(239, 68, 68, 0.35)',
        color: '#fee2e2',
        iconColor: '#f87171',
      },
      info: {
        background: 'rgba(59, 130, 246, 0.15)',
        border: '1px solid rgba(59, 130, 246, 0.35)',
        color: '#dbeafe',
        iconColor: '#60a5fa',
      },
    };

    const palette = palettes[toast.type] || palettes.info;
    const icon = toast.type === 'success' ? (
      <CheckCircle size={22} color={palette.iconColor} />
    ) : (
      <AlertCircle size={22} color={palette.iconColor} />
    );

    return (
      <div
        style={{
          position: 'fixed',
          top: '20px',
          right: '20px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          padding: '14px 18px',
          borderRadius: '12px',
          background: palette.background,
          border: palette.border,
          color: palette.color,
          boxShadow: '0 15px 35px rgba(15, 23, 42, 0.25)',
          zIndex: 9999,
          backdropFilter: 'blur(14px)',
        }}
      >
        {icon}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ fontWeight: 700, fontSize: '14px', letterSpacing: '0.2px' }}>{toast.title}</span>
          {toast.message ? (
            <span style={{ fontSize: '12px', opacity: 0.9 }}>{toast.message}</span>
          ) : null}
        </div>
      </div>
    );
  };

  const syncFileInputMode = (mode) => {
    const input = folderInputRef.current;
    if (!input) return;
    if (mode === 'files') {
      input.removeAttribute('webkitdirectory');
      input.removeAttribute('directory');
      input.setAttribute('accept', '.sql');
    } else {
      input.setAttribute('webkitdirectory', 'true');
      input.setAttribute('directory', 'true');
      input.setAttribute('accept', '.sql');
    }
    input.multiple = true;
  };

  useEffect(() => {
    syncFileInputMode(scriptSelectionMode);
  }, [scriptSelectionMode]);

  useEffect(() => {
    if (!isProcedurePanelActive) {
      setShouldReserveRightPanelSpace(false);
      return;
    }

    if (isRightPanelOpen) {
      setShouldReserveRightPanelSpace(true);
      return;
    }

    panelSpaceTimeoutRef.current = setTimeout(() => {
      setShouldReserveRightPanelSpace(false);
      panelSpaceTimeoutRef.current = null;
    }, PANEL_TRANSITION_DURATION);

    return () => {
      if (panelSpaceTimeoutRef.current) {
        clearTimeout(panelSpaceTimeoutRef.current);
        panelSpaceTimeoutRef.current = null;
      }
    };
  }, [isProcedurePanelActive, isRightPanelOpen]);

  const openFilePicker = (mode = scriptSelectionMode) => {
    const targetMode = mode || 'folder';
    if (targetMode !== scriptSelectionMode) {
      setScriptSelectionMode(targetMode);
    }
    syncFileInputMode(targetMode);
    const input = folderInputRef.current;
    if (!input) return;
    input.value = '';
    input.click();
  };

  // Simple fuzzy subsequence matcher: returns true if all characters of pattern
  // appear in order within the target string (case-insensitive)
  const fuzzyMatch = (pattern, target) => {
    if (!pattern) return true;
    if (!target) return false;
    const p = pattern.toLowerCase();
    const t = String(target).toLowerCase();
    let i = 0;
    for (let c of t) {
      if (c === p[i]) i++;
      if (i === p.length) return true;
    }
    return false;
  };

  // Removed legacy loadLineageReport; folder/zip buttons trigger inputs directly

  // Convert lineage report format to visualization format
  const convertLineageReportToVisualization = (reportArg, procedureReport = null) => {
    const report = (reportArg && typeof reportArg === 'object') ? reportArg : {};
    const tablesSection = (report.tables && typeof report.tables === 'object') ? report.tables : {};
    const columnsSection = (report.columns && typeof report.columns === 'object') ? report.columns : {};
    const tables = [];
    const connections = [];
    const sourceTables = new Set(); // Track source tables that need to be created
    const executableNames = new Set();

    if (procedureReport) {
      Object.keys(procedureReport.procedures || {}).forEach(name => executableNames.add(name));
      Object.keys(procedureReport.functions || {}).forEach(name => executableNames.add(name));
      Object.keys(procedureReport.triggers || {}).forEach(name => executableNames.add(name));
    }

    const tableEntries = Object.entries(tablesSection);

    const normalizeTableKey = (key) => {
      if (!key) return '';
      return key.replace(/\[/g, '').replace(/\]/g, '').toLowerCase();
    };

    const normalizedTableMap = new Map();
    tableEntries.forEach(([tableName, tableData]) => {
      const qualified = (tableData?.qualified_name || tableName || '').replace(/\[/g, '').replace(/\]/g, '');
      const tableOnly = tableData?.table_name || tableData?.name || qualified.split('.').pop();
      const schemaQualified = tableData?.schema ? `${tableData.schema}.${tableOnly}` : qualified;

      [tableName, qualified, schemaQualified, tableOnly, `${tableData?.schema || ''}.${tableOnly}`]
        .filter(Boolean)
        .forEach(keyVariant => {
          normalizedTableMap.set(normalizeTableKey(keyVariant), tableName);
        });
    });

    const resolveMetadataTableKey = (rawName) => {
      if (!rawName) return null;
      if (tablesSection?.[rawName]) {
        return rawName;
      }

      const normalized = normalizeTableKey(rawName);
      if (normalizedTableMap.has(normalized)) {
        return normalizedTableMap.get(normalized);
      }

      const trimmed = rawName.split('.').slice(-2).join('.');
      const trimmedNormalized = normalizeTableKey(trimmed);
      if (normalizedTableMap.has(trimmedNormalized)) {
        return normalizedTableMap.get(trimmedNormalized);
      }

      return null;
    };

    // First pass: collect all source tables from depends_on and source_columns
    tableEntries.forEach(([tableName, tableData]) => {
      // Add source tables from depends_on
      if (tableData.depends_on) {
        tableData.depends_on.forEach(depTable => {
          const metaKey = resolveMetadataTableKey(depTable);
          if (metaKey) {
            sourceTables.add(metaKey);
          } else {
            sourceTables.add(depTable);
          }
        });
      }
    });

    Object.entries(columnsSection || {}).forEach(([columnKey, columnData]) => {
      if (columnData.source_columns) {
        columnData.source_columns.forEach(sourceCol => {
          // Extract source table from fully qualified column name (e.g., "schema.table.column")
          const parts = sourceCol.split('.');
          if (parts.length >= 2) {
            // Join all parts except the last one to get the table name
            const sourceTable = parts.slice(0, -1).join('.');
            const metaKey = resolveMetadataTableKey(sourceTable);
            // Always add both the resolved key and original for comprehensive coverage
            if (metaKey) {
              sourceTables.add(metaKey);
            }
            // Always add the original source table name for column-level lineage tracking
            sourceTables.add(sourceTable);
          }
        });
      }
    });

    // Create virtual source tables for column-level lineage tracking
    // These are essential for visualizing column-to-column connections
    sourceTables.forEach(sourceTableName => {
      const metaKey = resolveMetadataTableKey(sourceTableName);
      const effectiveKey = metaKey || sourceTableName;
      const tableData = metaKey ? tablesSection?.[metaKey] : null;
      
      // Check if this table will be processed later from report.tables
      // If it exists in report.tables, we'll still create a virtual version if needed for column lineage
      const willBeProcessed = metaKey && tablesSection?.[metaKey];
      
      // Always create virtual tables for column-level lineage, even if table exists
      // This ensures we can track column-to-column connections properly
      const schema = tableData?.schema || (effectiveKey.includes('.') ? effectiveKey.split('.').slice(-2, -1)[0] : 'external');
      const tableDisplayName = tableData?.table_name || tableData?.name || (effectiveKey.includes('.') ? effectiveKey.split('.').pop() : effectiveKey);

      // Find ALL columns for this source table from source_columns references
      // This is critical for column-level lineage visualization
      const sourceColumns = new Set();
      Object.entries(columnsSection).forEach(([columnKey, columnData]) => {
        if (columnData.source_columns) {
          columnData.source_columns.forEach(sourceCol => {
            const parts = sourceCol.split('.');
            if (parts.length >= 2) {
              const sourceTableFromCol = parts.slice(0, -1).join('.');
              const columnName = parts[parts.length - 1];
              
              // Match against original name, resolved key, and normalized versions
              // This ensures we capture all column references even with different naming formats
              const matches = sourceTableFromCol === sourceTableName ||
                            sourceTableFromCol === effectiveKey ||
                            sourceTableFromCol === metaKey ||
                            normalizeTableKey(sourceTableFromCol) === normalizeTableKey(sourceTableName) ||
                            normalizeTableKey(sourceTableFromCol) === normalizeTableKey(effectiveKey);
              
              if (matches) {
                sourceColumns.add(columnName);
              }
            }
          });
        }
      });

      // Only create virtual table if it has columns from column lineage OR doesn't exist in report.tables
      // This ensures we create virtual tables for external sources referenced in column lineage
      if (sourceColumns.size > 0 || !willBeProcessed) {
        const sourceTable = {
          name: effectiveKey,
          schema,
          tableName: tableDisplayName,
          columns: Array.from(sourceColumns).map(colName => ({
            name: colName,
            type: 'string',
            sources: [],
            expression: 'source',
            fromMetadata: Boolean(tableData?.from_metadata),
          })),
          type: willBeProcessed ? (tableData?.definition_type === 'CREATE' ? 'target' : 'source') : 'source',
          file: tableData?.definition_script || (metaKey ? 'Metadata Catalog' : 'External Source'),
          fromMetadata: Boolean(tableData?.from_metadata),
          isVirtual: !willBeProcessed, // Mark as virtual if not in report.tables
        };

        tables.push(sourceTable);
      }
    });

    // Convert defined tables
    tableEntries.forEach(([tableName, tableData]) => {
      const fromMetadata = Boolean(tableData.from_metadata);
      const metadataColumnCount = tableData.metadata_column_count || 0;
      const tableColumns = Array.isArray(tableData.columns) ? tableData.columns : [];

      if (!fromMetadata && tableColumns.length === 0 && metadataColumnCount === 0) {
        return;
      }

      const schema = tableData.schema || (tableName.includes('.') ? tableName.split('.').slice(-2, -1)[0] : 'dbo');
      const displayName = tableData.table_name || tableData.name || (tableName.includes('.') ? tableName.split('.').pop() : tableName);

      const table = {
        name: tableName,
        schema,
        tableName: displayName,
        columns: tableColumns.map(colEntry => {
          const columnName = typeof colEntry === 'string'
            ? colEntry
            : colEntry?.name || colEntry?.column_name || colEntry?.column || colEntry?.target || '';
          const columnKey = columnName ? `${tableName}.${columnName}` : null;
          const columnData = columnKey ? columnsSection[columnKey] : undefined;
          const metadataType = typeof colEntry === 'object' ? (colEntry.data_type || colEntry.type) : undefined;
          const metadataNullable = typeof colEntry === 'object' ? colEntry.is_nullable : undefined;

          return {
            name: columnName || '(unknown)',
            type: columnData?.data_type || metadataType || 'string',
            sources: columnData?.source_columns || [],
            expression: columnData?.transforms?.[0] || 'column',
            dataType: columnData?.data_type || metadataType,
            isNullable: columnData?.is_nullable ?? metadataNullable,
            fromMetadata: columnData?.resolution_method === 'metadata' || fromMetadata || Boolean(metadataType),
          };
        }),
        type: Array.isArray(tableData.definition_types)
          ? (tableData.definition_types.includes('CREATE') || tableData.definition_types.includes('INSERT') ? 'target' : 'source')
          : (tableData.definition_type === 'CREATE' ? 'target' : 'source'),
        file: Array.isArray(tableData.definition_scripts) ? tableData.definition_scripts[0] : tableData.definition_script,
        fromMetadata,
        metadataColumnCount,
      };

      tables.push(table);
    });

    // Enrich existing source tables with columns inferred from source column references
    // This mirrors previous behavior where virtual source tables got their columns from references
    const sourceColumnsByTable = new Map();
    Object.entries(columnsSection).forEach(([columnKey, columnData]) => {
      if (!columnData?.source_columns) return;
      columnData.source_columns.forEach(sourceCol => {
        const parts = String(sourceCol).split('.');
        if (parts.length < 2) return;
        const sourceTableName = parts.slice(0, -1).join('.');
        const sourceColumnName = parts[parts.length - 1];
        if (!sourceColumnsByTable.has(sourceTableName)) {
          sourceColumnsByTable.set(sourceTableName, new Set());
        }
        sourceColumnsByTable.get(sourceTableName).add(sourceColumnName);
      });
    });

    tables.forEach(t => {
      if (!t || !Array.isArray(t.columns) || t.columns.length > 0) return;
      const inferredCols = sourceColumnsByTable.get(t.name);
      if (inferredCols && inferredCols.size > 0) {
        t.columns = Array.from(inferredCols).map(colName => ({
          name: colName,
          type: 'string',
          sources: [],
          expression: 'source'
        }));
      }
    });

    // Deduplicate tables by name, prioritizing metadata-backed versions
    const uniqueTableMap = new Map();
    tables.forEach(tbl => {
      if (!tbl) return;
      const key = tbl.name;
      if (!key) return;

      if (!uniqueTableMap.has(key)) {
        uniqueTableMap.set(key, tbl);
        return;
      }

      const existing = uniqueTableMap.get(key);
      const preferNew = (tbl.fromMetadata && !existing.fromMetadata) || (tbl.columns?.length || 0) > (existing.columns?.length || 0);
      if (preferNew) {
        uniqueTableMap.set(key, tbl);
      }
    });

    let normalizedTables = Array.from(uniqueTableMap.values());
    if (executableNames.size > 0) {
      normalizedTables = normalizedTables.filter(tbl => !executableNames.has(tbl.name));
    }
    const tableLookup = new Map(normalizedTables.map(t => [t.name, t]));

    // Convert column-level connections
    Object.entries(columnsSection).forEach(([columnKey, columnData]) => {
      // Column key format: "SalesLT_Silver.CustomerMaster.CustomerID"
      const parts = columnKey.split('.');
      const tableName = parts.slice(0, -1).join('.'); // Everything except last part
      const columnName = parts[parts.length - 1]; // Last part
      
      if (columnData.source_columns && columnData.source_columns.length > 0) {
        columnData.source_columns.forEach(sourceColumn => {
          // Source column format: "SalesLT.Customer.CustomerID"
          const sourceParts = sourceColumn.split('.');
          const sourceTable = sourceParts.slice(0, -1).join('.'); // Everything except last part
          const sourceCol = sourceParts[sourceParts.length - 1]; // Last part

          connections.push({
            sourceTable: sourceTable,
            sourceColumn: sourceCol,
            targetTable: tableName,
            targetColumn: columnName,
            transformationType: columnData.transforms?.[0] || 'direct'
          });

          // Add source to target column
          const targetTable = tableLookup.get(tableName);
          if (targetTable) {
            const targetCol = targetTable.columns.find(c => c.name === columnName);
                        if (targetCol) {
                          targetCol.sources.push({ 
                table: sourceTable, 
                column: sourceCol 
              });
            }
          }
        });
      }
    });

    return {
      tables: normalizedTables,
      connections,
      errors: []
    };
  };

  // Convert procedure lineage report format to visualization format
  const convertProcedureLineageToVisualization = (procReport) => {
    const nodes = [];
    const connections = [];
    
    // Build set of all procedure/function/trigger names to filter them out from table lists
    const allProcFuncNames = new Set();
    if (procReport.procedures) {
      Object.keys(procReport.procedures).forEach(name => allProcFuncNames.add(name));
    }
    if (procReport.functions) {
      Object.keys(procReport.functions).forEach(name => allProcFuncNames.add(name));
    }
    if (procReport.triggers) {
      Object.keys(procReport.triggers).forEach(name => allProcFuncNames.add(name));
    }
    
    // Add all procedures as nodes
    if (procReport.procedures) {
      Object.entries(procReport.procedures).forEach(([procName, procData]) => {
        const [schema, name] = procName.includes('.') 
                    ? procName.split('.') 
                    : ['default', procName];
        
        const node = {
          name: procName,
          schema: schema,
          nodeName: name,
          type: 'procedure',
          file: procData.file_path || 'Unknown',
          parameters: procData.parameters || [],
          reads_tables: procData.reads_tables || [],
          writes_tables: procData.writes_tables || [],
          calls_procedures: procData.calls_procedures || [],
          called_by: procData.called_by || [],
          complexity_score: procData.complexity_score || 0
        };
        
        nodes.push(node);
        
        // Add connections for procedure calls
        if (procData.calls_procedures) {
          procData.calls_procedures.forEach(callee => {
            connections.push({
              source: procName,
              target: callee,
              type: 'procedure_call',
              label: 'calls'
            });
          });
        }
        
        // Add connections for called_by
        if (procData.called_by) {
          procData.called_by.forEach(caller => {
            connections.push({
              source: caller,
              target: procName,
              type: 'procedure_call',
              label: 'called_by'
            });
          });
        }
        
        // Add connections for table reads
        // Filter out procedure/function names that might have been incorrectly added
        if (procData.reads_tables) {
          procData.reads_tables.forEach(table => {
            // Skip if this is actually a procedure/function name, not a table
            if (allProcFuncNames.has(table)) {
              return;
            }
            
            connections.push({
              source: table,
              target: procName,
              type: 'table_read',
              label: 'reads'
            });
            // Add table as a node if not already added
            if (!nodes.find(n => n.name === table && n.type === 'table')) {
              const [tblSchema, tblName] = table.includes('.') 
                            ? table.split('.') 
                            : ['default', table];
              nodes.push({
                name: table,
                schema: tblSchema,
                nodeName: tblName,
                type: 'table',
                file: 'External',
                isTemp: table.startsWith('#')
              });
            }
          });
        }
        
        // Add connections for table writes
        // Filter out procedure/function names that might have been incorrectly added
        if (procData.writes_tables) {
          procData.writes_tables.forEach(table => {
            // Skip if this is actually a procedure/function name, not a table
            if (allProcFuncNames.has(table)) {
              return;
            }
            
            connections.push({
              source: procName,
              target: table,
              type: 'table_write',
              label: 'writes'
            });
            // Add table as a node if not already added
            if (!nodes.find(n => n.name === table && n.type === 'table')) {
              const [tblSchema, tblName] = table.includes('.') 
                            ? table.split('.') 
                            : ['default', table];
              nodes.push({
                name: table,
                schema: tblSchema,
                nodeName: tblName,
                type: 'table',
                file: 'External',
                isTemp: table.startsWith('#')
              });
            }
          });
        }

        // Ensure temp tables exist and link creation
        (procData.creates_temp_tables || []).forEach(table => {
          if (!nodes.find(n => n.name === table && n.type === 'table')) {
            const [tblSchema, tblName] = table.includes('.') ? table.split('.') : ['default', table];
            nodes.push({ name: table, schema: tblSchema, nodeName: tblName, type: 'table', file: 'External', isTemp: true });
          }
          connections.push({ source: procName, target: table, type: 'table_create', label: 'creates' });
        });

        // Column-level connections (reads/writes/updates)
        const ensureColumnNode = (fqcol) => {
          const partsAll = String(fqcol).split('.');
          // Only create column node if it looks like schema.table.column (>=3 parts)
          if (partsAll.length < 3) return false;
          if (!nodes.find(n => n.name === fqcol && n.type === 'column')) {
            const parts = [...partsAll];
            const colName = parts.pop();
            const tableName = parts.join('.');
            const [tblSchema, tblName] = tableName.includes('.') ? tableName.split('.') : ['default', tableName];
            nodes.push({
              name: fqcol,
              schema: tblSchema,
              nodeName: colName,
              type: 'column',
              parentTable: tableName
            });
            // Also ensure table node exists
            if (tableName && !nodes.find(n => n.name === tableName && n.type === 'table')) {
              nodes.push({ name: tableName, schema: tblSchema, nodeName: tblName, type: 'table', file: 'External' });
            }
            // Optional: link column to table for layout cohesion
            connections.push({ source: tableName, target: fqcol, type: 'column_of', label: 'of' });
          }
          return true;
        };
        (procData.columns_read || []).forEach(fqcol => {
          const created = ensureColumnNode(fqcol);
          if (created) {
            connections.push({ source: fqcol, target: procName, type: 'column_read', label: 'reads' });
          } else {
            // treat as table read if only table was provided
            if (String(fqcol).split('.').length >= 2) {
              connections.push({ source: String(fqcol), target: procName, type: 'table_read', label: 'reads' });
            }
          }
        });
        (procData.columns_written || []).forEach(fqcol => {
          const created = ensureColumnNode(fqcol);
          if (created) {
            connections.push({ source: procName, target: fqcol, type: 'column_write', label: 'writes' });
          } else {
            if (String(fqcol).split('.').length >= 2) {
              connections.push({ source: procName, target: String(fqcol), type: 'table_write', label: 'writes' });
            }
          }
        });
        (procData.columns_updated || []).forEach(fqcol => {
          const created = ensureColumnNode(fqcol);
          if (created) {
            connections.push({ source: procName, target: fqcol, type: 'column_update', label: 'updates' });
          } else {
            if (String(fqcol).split('.').length >= 2) {
              connections.push({ source: procName, target: String(fqcol), type: 'table_write', label: 'updates' });
            }
          }
        });
      });
    }
    
    // Add all functions as nodes
    if (procReport.functions) {
      Object.entries(procReport.functions).forEach(([funcName, funcData]) => {
        const [schema, name] = funcName.includes('.') 
                    ? funcName.split('.') 
                    : ['default', funcName];
        
        const node = {
          name: funcName,
          schema: schema,
          nodeName: name,
          type: 'function',
          file: funcData.file_path || 'Unknown',
          parameters: funcData.parameters || [],
          return_type: funcData.return_type,
          is_table_valued: funcData.is_table_valued || false,
          reads_tables: funcData.reads_tables || [],
          writes_tables: funcData.writes_tables || [],
          called_by: funcData.called_by || [],
          complexity_score: funcData.complexity_score || 0
        };
        
        nodes.push(node);
        
        // Add connections for called_by
        if (funcData.called_by) {
          funcData.called_by.forEach(caller => {
            connections.push({
              source: caller,
              target: funcName,
              type: 'function_call',
              label: 'called_by'
            });
          });
        }
        
        // Add connections for table reads
        if (funcData.reads_tables) {
          funcData.reads_tables.forEach(table => {
            // Skip if this is actually a procedure/function name, not a table
            if (allProcFuncNames.has(table)) {
              return;
            }
            
            connections.push({
              source: table,
              target: funcName,
              type: 'table_read',
              label: 'reads'
            });
            // Add table as a node if not already added
            if (!nodes.find(n => n.name === table && n.type === 'table')) {
              const [tblSchema, tblName] = table.includes('.') 
                            ? table.split('.') 
                            : ['default', table];
              nodes.push({
                name: table,
                schema: tblSchema,
                nodeName: tblName,
                type: 'table',
                file: 'External',
                isTemp: table.startsWith('#')
              });
            }
          });
        }
        
        // Add connections for table writes
        if (funcData.writes_tables) {
          funcData.writes_tables.forEach(table => {
            // Skip if this is actually a procedure/function name, not a table
            if (allProcFuncNames.has(table)) {
              return;
            }
            
            connections.push({
              source: funcName,
              target: table,
              type: 'table_write',
              label: 'writes'
            });
            // Add table as a node if not already added
            if (!nodes.find(n => n.name === table && n.type === 'table')) {
              const [tblSchema, tblName] = table.includes('.') 
                            ? table.split('.') 
                            : ['default', table];
              nodes.push({
                name: table,
                schema: tblSchema,
                nodeName: tblName,
                type: 'table',
                file: 'External',
                isTemp: table.startsWith('#')
              });
            }
          });
        }

        // Column-level connections for functions
        const ensureFuncColumnNode = (fqcol) => {
          const partsAll = String(fqcol).split('.');
          if (partsAll.length < 3) return false;
          if (!nodes.find(n => n.name === fqcol && n.type === 'column')) {
            const parts = [...partsAll];
            const colName = parts.pop();
            const tableName = parts.join('.');
            const [tblSchema, tblName] = tableName.includes('.') ? tableName.split('.') : ['default', tableName];
            nodes.push({ name: fqcol, schema: tblSchema, nodeName: colName, type: 'column', parentTable: tableName });
            if (tableName && !nodes.find(n => n.name === tableName && n.type === 'table')) {
              nodes.push({ name: tableName, schema: tblSchema, nodeName: tblName, type: 'table', file: 'External' });
            }
            connections.push({ source: tableName, target: fqcol, type: 'column_of', label: 'of' });
          }
          return true;
        };
        (funcData.columns_read || []).forEach(fqcol => {
          const created = ensureFuncColumnNode(fqcol);
          if (created) {
            connections.push({ source: fqcol, target: funcName, type: 'column_read', label: 'reads' });
          } else {
            if (String(fqcol).split('.').length >= 2) {
              connections.push({ source: String(fqcol), target: funcName, type: 'table_read', label: 'reads' });
            }
          }
        });
        (funcData.columns_written || []).forEach(fqcol => {
          const created = ensureFuncColumnNode(fqcol);
          if (created) {
            connections.push({ source: funcName, target: fqcol, type: 'column_write', label: 'writes' });
          } else {
            if (String(fqcol).split('.').length >= 2) {
              connections.push({ source: funcName, target: String(fqcol), type: 'table_write', label: 'writes' });
            }
          }
        });
      });
    }
    
    // Add all triggers as nodes
    if (procReport.triggers) {
      Object.entries(procReport.triggers).forEach(([trgName, trgData]) => {
        const [schema, name] = trgName.includes('.') 
                    ? trgName.split('.') 
                    : ['default', trgName];
        const node = {
          name: trgName,
          schema: schema,
          nodeName: name,
          type: 'trigger',
          file: trgData.file_path || 'Unknown',
          reads_tables: trgData.reads_tables || [],
          writes_tables: trgData.writes_tables || [],
          complexity_score: trgData.complexity_score || 0
        };
        nodes.push(node);
        // Table reads
        (trgData.reads_tables || []).forEach(table => {
          connections.push({ source: table, target: trgName, type: 'table_read', label: 'reads' });
          if (!nodes.find(n => n.name === table && n.type === 'table')) {
            const [tblSchema, tblName] = table.includes('.') ? table.split('.') : ['default', table];
            nodes.push({ name: table, schema: tblSchema, nodeName: tblName, type: 'table', file: 'External', isTemp: table.startsWith('#') });
          }
        });
        // Table writes
        (trgData.writes_tables || []).forEach(table => {
          connections.push({ source: trgName, target: table, type: 'table_write', label: 'writes' });
          if (!nodes.find(n => n.name === table && n.type === 'table')) {
            const [tblSchema, tblName] = table.includes('.') ? table.split('.') : ['default', table];
            nodes.push({ name: table, schema: tblSchema, nodeName: tblName, type: 'table', file: 'External', isTemp: table.startsWith('#') });
          }
        });
      });
    }
    
    return {
      nodes,
      connections,
      errors: []
    };
  };

  // Safely convert any value to a displayable string to avoid rendering objects in JSX
  const toDisplay = (value) => {
    if (value == null) return '';
    if (typeof value === 'object') {
      if (value.column) return String(value.column);
      if (value.name) return String(value.name);
      if (value.expr) return String(value.expr.type || 'expr');
      try {
        return JSON.stringify(value);
    } catch (_) {
        return String(value);
    }
    }
    return String(value);
  };

  const layoutTablesWithDagre = (tables, connections) => {
    if (!tables || !connections) return [];
    
    // Standardized height constants - must match renderLineage function
    const columnHeight = 28;
    const tableHeaderHeight = 60; // Increased to accommodate table name and schema
    const tablePadding = 12; // Changed from 16 to match renderLineage
    const columnSpacing = 4; // Added for column marginBottom
    const tableBottomMargin = 15; // Additional margin at bottom of table
    const tableWidth = 320;

    const calculateTableHeight = (table) => {
      const isExpanded = expandedTables.has(table.name);
      if (!isExpanded) return tableHeaderHeight;
      
      // Calculate height more accurately
      const columnsHeight = table.columns.length > 0 
        ? (table.columns.length * columnHeight) + ((table.columns.length - 1) * columnSpacing)
        : 0;
      
      return tableHeaderHeight + tablePadding + columnsHeight + tablePadding + tableBottomMargin;
    };

    // Filter to only connected tables (tables that have at least one connection)
    const connectedTables = getConnectedTables(tables, connections);

    // Get visible tables - respect focus mode
    let visibleTables;
    if (focusedTable && focusedTableConnections.size > 0) {
      // In focus mode, only show focused table and its immediate connections
      visibleTables = connectedTables.filter(table => 
        focusedTableConnections.has(table.name) &&
        !hiddenPreviousLevels?.has(table.name) && 
        !hiddenNextLevels?.has(table.name)
      );
    } else {
      // Normal mode - show all connected tables except hidden ones
      visibleTables = connectedTables.filter(table => !hiddenPreviousLevels?.has(table.name) && !hiddenNextLevels?.has(table.name));
    }
    
    // Check if we need to recalculate layout (new tables appeared, first time, significant height changes, or focus mode changed)
    const needsLayout = visibleTables.some(table => {
      if (!tablePositionsRef.current.has(table.name)) return true;
      
      // Check if height has changed significantly (more than just minor adjustments)
      const storedHeight = tablePositionsRef.current.get(table.name).height;
      const currentHeight = calculateTableHeight(table);
      const heightDifference = Math.abs(storedHeight - currentHeight);
      
      // If height difference is significant (more than 10px), recalculate layout
      return heightDifference > 10;
    }) || 
    // Force layout recalculation when focus mode changes (tables are added/removed from visible set)
    (focusedTable && focusedTableConnections.size > 0 && 
     visibleTables.length !== Object.keys(tablePositionsRef.current).length);
    
    if (needsLayout) {
      // Clear existing positions for tables that are no longer visible
      const visibleTableNames = new Set(visibleTables.map(t => t.name));
      const existingTableNames = Array.from(tablePositionsRef.current.keys());
      existingTableNames.forEach(tableName => {
        if (!visibleTableNames.has(tableName)) {
          tablePositionsRef.current.delete(tableName);
        }
      });

      // Create new dagre graph for layout calculation
      const g = new dagre.graphlib.Graph();
      g.setGraph({ 
        rankdir: 'LR', 
        ranksep: 300, 
        nodesep: 100,
        edgesep: 50,
        marginx: 50,
        marginy: 50
      });
      g.setDefaultEdgeLabel(() => ({}));

      // Add all visible tables to graph
      visibleTables.forEach(table => {
        const height = calculateTableHeight(table);
        g.setNode(table.name, { 
          label: table.name, 
          width: tableWidth, 
          height: height 
        });
      });

      // Add edges (filter out connections involving hidden tables)
      const addedEdges = new Set();
      connections.forEach(conn => {
        const edgeKey = `${conn.sourceTable}->${conn.targetTable}`;
        if (!addedEdges.has(edgeKey) && 
            visibleTableNames.has(conn.sourceTable) && 
            visibleTableNames.has(conn.targetTable)) {
          g.setEdge(conn.sourceTable, conn.targetTable);
          addedEdges.add(edgeKey);
        }
      });

      // Calculate layout
      dagre.layout(g);

      // Update positions map with new positions
      visibleTables.forEach(table => {
        const node = g.node(table.name);
        if (node) {
          tablePositionsRef.current.set(table.name, {
            x: node.x - node.width / 2,
            y: node.y - node.height / 2,
            width: node.width,
            height: node.height
          });
        }
      });
    }

    // Apply stable positions to tables, updating heights for expansion changes
    const layoutedTables = visibleTables.map(table => {
      const position = tablePositionsRef.current.get(table.name);
      if (!position) return null; // Skip if no position available yet
      
      const currentHeight = calculateTableHeight(table);
      
      return {
        ...table,
        x: position.x,
        y: position.y,
        width: position.width,
        height: currentHeight // Use current height for expansion changes
      };
    }).filter(Boolean); // Remove null entries

    return layoutedTables;
  };

  // Removed analyzeAll; folder/zip flows are primary entry points now

  const handleAnalyzeScript = () => {
    setUseEnhancedFlow(false);
    setMetadataFetched(false);
    setScriptSelectionMode('folder');
    setPendingAction('script');
    setShowDialectPicker(true);
  };

  // Zip upload flow removed

  const uploadFolderToServer = async (files) => {
    const useEnhanced = useEnhancedFlow && selectedDialect === 'tsql' && metadataFilePath;

    setIsAnalyzing(true);
    try {
      const formData = new FormData();

      // Add all files to FormData, preserving relative paths when available
      files.forEach(file => {
        const relativeName = file.webkitRelativePath || file.name;
        formData.append('files', file, relativeName);
      });

      // Optionally include connection details for dialect-specific analysis
      if (selectedDialect === 'tsql' && connectionDetails) {
        formData.append('connection', JSON.stringify({
          dialect: selectedDialect,
          server: connectionDetails.server || '',
          database: connectionDetails.database || '',
          username: connectionDetails.username || '',
          password: connectionDetails.password || '',
          driver: connectionDetails.driver || 'ODBC Driver 18 for SQL Server'
        }));
      }

      if (useEnhanced) {
        formData.append('metadata_path', metadataFilePath);
        formData.append('dialect', selectedDialect || 'tsql');
      }

      // Add OpenAI key if provided (only for analyze script, not connection)
      if (useOpenAI && openAIKey) {
        formData.append('openai_key', openAIKey);
      }

      const endpoint = useEnhanced
        ? 'http://localhost:8000/api/analyze/enhanced'
        : `http://localhost:8000/api/analyze?dialect=${encodeURIComponent(selectedDialect || 'tsql')}`;

      const response = await fetch(endpoint, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        let errorMessage = 'Failed to analyze folder';
        try {
          const errorData = await response.json();
          if (errorData?.detail) errorMessage = errorData.detail;
        } catch (_) {
          // swallow JSON parse errors
        }
        throw new Error(errorMessage);
      }

      const payload = await response.json();
      const statementReport = payload?.statement_report || payload;
      const procedureReport = payload?.procedure_report || null;
      const combinedSummary = payload?.combined_summary || null;

      setLineageReport(statementReport);
      if (combinedSummary) setSummaryReport(combinedSummary); else setSummaryReport(null);
      if (procedureReport) {
        setProcedureLineage(procedureReport);
        const procConvertedData = convertProcedureLineageToVisualization(procedureReport);
        setProcedureLineageData(procConvertedData);
        setExpandedProcedures(new Set([
          ...Object.keys(procedureReport.procedures || {}),
          ...Object.keys(procedureReport.functions || {})
        ]));
      } else {
        setProcedureLineage(null);
        setProcedureLineageData(null);
      }

      // Convert report to visualization format
      const convertedData = convertLineageReportToVisualization(statementReport, procedureReport);
      setLineageData(convertedData);
      // Expand all tables by default
      setExpandedTables(new Set(convertedData.tables.map(table => table.name)));
      
      // Initialize hidden levels - start with empty sets to show all tables initially
      setHiddenPreviousLevels(new Set());
      setHiddenNextLevels(new Set());
      tablePositionsRef.current = new Map(); // Clear positions for fresh layout

      updateLineageNotice(statementReport, procedureReport, convertedData, { isMetadata: useEnhanced });

      setMetadataFetched(false);
      setShowStart(false);
      setAnalysisError(null); // Clear any previous errors
      showToast(
        'Analysis complete',
        useEnhanced ? 'Enhanced lineage generated with metadata context.' : 'Lineage analysis ready.',
        'success'
      );
    } catch (error) {
      console.error('Error uploading folder:', error);
      const errorMessage = error.message || 'Unknown error occurred during analysis';
      setAnalysisError(errorMessage);
      showToast('Failed to analyze scripts', errorMessage, 'error');
    } finally {
      setIsAnalyzing(false);
      setUseEnhancedFlow(false);
    }
  };

  const handleStartAnalyzeCodebase = () => {
    setUseEnhancedFlow(false);
    setMetadataFetched(false);
    setScriptSelectionMode('folder');
    setPendingAction('codebase');
    setShowDialectPicker(true);
  };

  const handleConnectionBack = () => {
    setShowConnectionForm(false);
    setUseEnhancedFlow(false);
    setMetadataFetched(false);
    setScriptSelectionMode('folder');
  };

  const handleTsqlMetadataFetch = async () => {
    const trimmed = {
      server: (connectionDetails.server || '').trim(),
      database: (connectionDetails.database || '').trim(),
      username: (connectionDetails.username || '').trim(),
      password: connectionDetails.password || '',
      driver: (connectionDetails.driver || 'ODBC Driver 18 for SQL Server').trim(),
    };

    const missingFields = Object.entries({
      server: trimmed.server,
      database: trimmed.database,
      username: trimmed.username,
      password: trimmed.password,
    }).filter(([, value]) => !value);

    if (missingFields.length > 0) {
      showToast('Connection details missing', 'Please complete all fields before continuing.', 'error');
      return;
    }

    try {
      setMetadataFetched(false);
      setIsConnectionSubmitting(true);
      const response = await fetch('http://localhost:8000/api/metadata/tsql', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          ...trimmed,
          dialect: selectedDialect || 'tsql',
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to extract database metadata');
      }

      const result = await response.json();
      if (result?.saved_to) {
        setMetadataFilePath(result.saved_to);
      }

      showToast('Metadata extraction complete', 'Metadata cached successfully. Select SQL scripts to analyze.', 'success');
      setMetadataFetched(true);
    } catch (error) {
      console.error('Metadata extraction failed:', error);
      showToast('Failed to extract metadata', error.message || 'Unknown error', 'error');
    } finally {
      setIsConnectionSubmitting(false);
    }
  };

  const handleTeradataMetadataFetch = async () => {
    const trimmed = {
      host: (connectionDetails.host || connectionDetails.server || '').trim(),
      database: (connectionDetails.database || '').trim(),
      username: (connectionDetails.username || '').trim(),
      password: connectionDetails.password || '',
      logmech: (connectionDetails.logmech || 'TD2').trim() || 'TD2',
      charset: (connectionDetails.charset || 'UTF8').trim() || 'UTF8',
      tmode: (connectionDetails.tmode || 'ANSI').trim() || 'ANSI',
      encryptdata: connectionDetails.encryptdata !== false,
    };

    const missingFields = Object.entries({
      host: trimmed.host,
      database: trimmed.database,
      username: trimmed.username,
      password: trimmed.password,
    }).filter(([, value]) => !value);

    if (missingFields.length > 0) {
      showToast('Connection details missing', 'Please complete all fields before continuing.', 'error');
      return;
    }

    try {
      setMetadataFetched(false);
      setIsConnectionSubmitting(true);
      const response = await fetch('http://localhost:8000/api/metadata/teradata', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(trimmed),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to extract Teradata metadata');
      }

      const result = await response.json();
      if (result?.saved_to) {
        setMetadataFilePath(result.saved_to);
      }

      showToast('Metadata extraction complete', 'Teradata metadata cached successfully.', 'success');
      setMetadataFetched(true);
    } catch (error) {
      console.error('Teradata metadata extraction failed:', error);
      showToast('Failed to extract metadata', error.message || 'Unknown error', 'error');
    } finally {
      setIsConnectionSubmitting(false);
    }
  };

  const handlePostgresMetadataFetch = async () => {
    const host = (connectionDetails.host || connectionDetails.server || '').trim();
    const database = (connectionDetails.database || '').trim();
    const username = (connectionDetails.username || '').trim();
    const password = connectionDetails.password || '';
    const portValue = connectionDetails.port || '5432';
    const port = Number.isNaN(parseInt(portValue, 10)) ? 5432 : parseInt(portValue, 10);

    const missingFields = Object.entries({
      host,
      database,
      username,
      password,
    }).filter(([, value]) => !value);

    if (missingFields.length > 0) {
      showToast('Connection details missing', 'Please complete all fields before continuing.', 'error');
      return;
    }

    try {
      setMetadataFetched(false);
      setIsConnectionSubmitting(true);
      const response = await fetch('http://localhost:8000/api/metadata/postgres', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host, database, username, password, port }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to extract PostgreSQL metadata');
      }

      const result = await response.json();
      if (result?.saved_to) {
        setMetadataFilePath(result.saved_to);
      }

      showToast('Metadata extraction complete', 'PostgreSQL metadata cached successfully.', 'success');
      setMetadataFetched(true);
    } catch (error) {
      console.error('PostgreSQL metadata extraction failed:', error);
      showToast('Failed to extract metadata', error.message || 'Unknown error', 'error');
    } finally {
      setIsConnectionSubmitting(false);
    }
  };

  const handleOracleMetadataFetch = async () => {
    const host = (connectionDetails.host || connectionDetails.server || '').trim();
    const serviceName = (connectionDetails.serviceName || connectionDetails.database || '').trim();
    const username = (connectionDetails.username || '').trim();
    const password = connectionDetails.password || '';
    const portValue = connectionDetails.port || '1521';
    const port = Number.isNaN(parseInt(portValue, 10)) ? 1521 : parseInt(portValue, 10);
    const targetSchemas = (connectionDetails.targetSchemas || '')
      .split(',')
      .map(schema => schema.trim())
      .filter(Boolean);

    const missingFields = Object.entries({
      host,
      serviceName,
      username,
      password,
    }).filter(([, value]) => !value);

    if (missingFields.length > 0) {
      showToast('Connection details missing', 'Please complete all fields before continuing.', 'error');
      return;
    }

    try {
      setMetadataFetched(false);
      setIsConnectionSubmitting(true);
      const response = await fetch('http://localhost:8000/api/metadata/oracle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          host,
          service_name: serviceName,
          username,
          password,
          port,
          target_schemas: targetSchemas.length ? targetSchemas : undefined,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to extract Oracle metadata');
      }

      const result = await response.json();
      if (result?.saved_to) {
        setMetadataFilePath(result.saved_to);
      }

      showToast('Metadata extraction complete', 'Oracle metadata cached successfully.', 'success');
      setMetadataFetched(true);
    } catch (error) {
      console.error('Oracle metadata extraction failed:', error);
      showToast('Failed to extract metadata', error.message || 'Unknown error', 'error');
    } finally {
      setIsConnectionSubmitting(false);
    }
  };

  const handleFetchMetadata = async () => {
    switch ((selectedDialect || '').toLowerCase()) {
      case 'tsql':
      case 'mssql':
        await handleTsqlMetadataFetch();
        return;
      case 'teradata':
        await handleTeradataMetadataFetch();
        return;
      case 'postgres':
      case 'postgresql':
      case 'postgress':
      case 'pgsql':
        await handlePostgresMetadataFetch();
        return;
      case 'oracle':
        await handleOracleMetadataFetch();
        return;
      default:
        showToast('Unsupported dialect', 'Metadata extraction is not available for this dialect yet.', 'error');
    }
  };

  const handleMetadataProceed = async () => {
    const dialect = (selectedDialect || '').toLowerCase();

    if (dialect === 'snowflake') {
      await handleSnowflakeMetadataAnalysis();
      return;
    }

    const requiresMetadata = (label) => {
      if (!metadataFetched) {
        showToast('Metadata missing', `Please fetch ${label} metadata before continuing.`, 'error');
        return false;
      }
      return true;
    };

    if (dialect === 'teradata') {
      if (!requiresMetadata('Teradata')) return;
      await handleTeradataMetadataAnalysis();
      return;
    }

    if (dialect === 'tsql' || dialect === 'mssql') {
      if (!requiresMetadata('T-SQL')) return;
      await handleDirectMetadataAnalysis();
      return;
    }

    if (['postgres', 'postgresql', 'postgress', 'pgsql'].includes(dialect)) {
      if (!requiresMetadata('PostgreSQL')) return;
      await handlePostgresMetadataAnalysis();
      return;
    }

    if (dialect === 'oracle') {
      if (!requiresMetadata('Oracle')) return;
      await handleOracleMetadataAnalysis();
      return;
    }

    showToast('Unsupported dialect', 'Metadata analysis is not available for this dialect yet.', 'error');
  };

  const applyAnalysisResults = (payload, successMessage) => {
    const statementReport = payload?.statement_report || payload;
    const procedureReport = payload?.procedure_report || null;
    const combinedSummary = payload?.combined_summary || null;

    setLineageReport(statementReport);
    if (combinedSummary) setSummaryReport(combinedSummary); else setSummaryReport(null);
    if (procedureReport) {
      setProcedureLineage(procedureReport);
      const procConvertedData = convertProcedureLineageToVisualization(procedureReport);
      setProcedureLineageData(procConvertedData);
      setExpandedProcedures(new Set([
        ...Object.keys(procedureReport.procedures || {}),
        ...Object.keys(procedureReport.functions || {})
      ]));
    } else {
      setProcedureLineage(null);
      setProcedureLineageData(null);
    }

    const convertedData = convertLineageReportToVisualization(statementReport, procedureReport);
    setLineageData(convertedData);
    setExpandedTables(new Set(convertedData.tables.map(table => table.name)));
    setHiddenPreviousLevels(new Set());
    setHiddenNextLevels(new Set());
    tablePositionsRef.current = new Map();

    updateLineageNotice(statementReport, procedureReport, convertedData, { isMetadata: true });

    setShowStart(false);
    setShowConnectionForm(false);
    setAnalysisError(null);
    showToast('Analysis complete', successMessage, 'success');
  };

  const handleDirectMetadataAnalysis = async () => {
    const trimmed = {
      server: (connectionDetails.server || '').trim(),
      database: (connectionDetails.database || '').trim(),
      username: (connectionDetails.username || '').trim(),
      password: connectionDetails.password || '',
      driver: (connectionDetails.driver || 'ODBC Driver 18 for SQL Server').trim(),
    };

    const missingFields = Object.entries({
      server: trimmed.server,
      database: trimmed.database,
      username: trimmed.username,
      password: trimmed.password,
    }).filter(([, value]) => !value);

    if (missingFields.length > 0) {
      showToast('Connection details missing', 'Please complete all fields before continuing.', 'error');
      return;
    }

    setIsAnalyzing(true);
    try {
      const requestBody = {
        ...trimmed,
        dialect: selectedDialect || 'tsql',
        ollama_url: 'http://localhost:11434',
        ollama_model: 'qwen2.5-coder:14b',
        openai_model: 'gpt-4o-mini',
        batch_size: 10,
        timeout: 300,
      };

      if (useOpenAI && openAIKey) {
        requestBody.openai_api_key = openAIKey;
      }

      if (metadataFilePath) {
        requestBody.metadata_file_path = metadataFilePath;
      }

      const response = await fetch('http://localhost:8000/api/analyze/metadata', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        let errorMessage = 'Failed to analyze database';
        try {
          const errorData = await response.json();
          if (errorData?.detail) errorMessage = errorData.detail;
        } catch (_) {
          // swallow JSON parse errors
        }
        throw new Error(errorMessage);
      }

      const payload = await response.json();
      applyAnalysisResults(payload, 'Metadata-based lineage analysis completed successfully.');
    } catch (error) {
      console.error('Error analyzing database:', error);
      const errorMessage = error.message || 'Unknown error occurred during analysis';
      setAnalysisError(errorMessage);
      showToast('Failed to analyze database', errorMessage, 'error');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleTeradataMetadataAnalysis = async () => {
    const trimmed = {
      host: (connectionDetails.host || connectionDetails.server || '').trim(),
      database: (connectionDetails.database || '').trim(),
      username: (connectionDetails.username || '').trim(),
      password: connectionDetails.password || '',
      logmech: (connectionDetails.logmech || 'TD2').trim() || 'TD2',
      charset: (connectionDetails.charset || 'UTF8').trim() || 'UTF8',
      tmode: (connectionDetails.tmode || 'ANSI').trim() || 'ANSI',
      encryptdata: connectionDetails.encryptdata !== false,
    };

    const missingFields = Object.entries({
      host: trimmed.host,
      database: trimmed.database,
      username: trimmed.username,
      password: trimmed.password,
    }).filter(([, value]) => !value);

    if (missingFields.length > 0) {
      showToast('Connection details missing', 'Please complete all fields before continuing.', 'error');
      return;
    }

    setIsAnalyzing(true);
    try {
      const requestBody = {
        ...trimmed,
        dialect: 'teradata',
        debug: false,
        ollama_url: 'http://localhost:11434',
        ollama_model: 'qwen2.5-coder:14b',
        openai_model: 'gpt-4o-mini',
        batch_size: 10,
        timeout: 300,
      };

      if (useOpenAI && openAIKey) {
        requestBody.openai_api_key = openAIKey;
      }

      if (metadataFilePath) {
        requestBody.metadata_file_path = metadataFilePath;
      }

      const response = await fetch('http://localhost:8000/api/analyze/metadata/teradata', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        let errorMessage = 'Failed to analyze Teradata database';
        try {
          const errorData = await response.json();
          if (errorData?.detail) errorMessage = errorData.detail;
        } catch (_) {
          // ignore
        }
        throw new Error(errorMessage);
      }

      const payload = await response.json();
      applyAnalysisResults(payload, 'Teradata metadata analysis completed successfully.');
    } catch (error) {
      console.error('Error analyzing Teradata database:', error);
      const errorMessage = error.message || 'Unknown error occurred during analysis';
      setAnalysisError(errorMessage);
      showToast('Failed to analyze database', errorMessage, 'error');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handlePostgresMetadataAnalysis = async () => {
    const host = (connectionDetails.host || connectionDetails.server || '').trim();
    const database = (connectionDetails.database || '').trim();
    const username = (connectionDetails.username || '').trim();
    const password = connectionDetails.password || '';
    const portValue = connectionDetails.port || '5432';
    const port = Number.isNaN(parseInt(portValue, 10)) ? 5432 : parseInt(portValue, 10);

    const missingFields = Object.entries({
      host,
      database,
      username,
      password,
    }).filter(([, value]) => !value);

    if (missingFields.length > 0) {
      showToast('Connection details missing', 'Please complete all fields before continuing.', 'error');
      return;
    }

    setIsAnalyzing(true);
    try {
      const requestBody = {
        host,
        database,
        username,
        password,
        port,
        dialect: 'postgres',
        debug: false,
        ollama_url: 'http://localhost:11434',
        ollama_model: 'qwen2.5-coder:14b',
        openai_model: 'gpt-4o-mini',
        batch_size: 10,
        timeout: 300,
      };

      if (useOpenAI && openAIKey) {
        requestBody.openai_api_key = openAIKey;
      }

      if (metadataFilePath) {
        requestBody.metadata_file_path = metadataFilePath;
      }

      const response = await fetch('http://localhost:8000/api/analyze/metadata/postgres', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        let errorMessage = 'Failed to analyze PostgreSQL database';
        try {
          const errorData = await response.json();
          if (errorData?.detail) errorMessage = errorData.detail;
        } catch (_) {
          // ignore
        }
        throw new Error(errorMessage);
      }

      const payload = await response.json();
      applyAnalysisResults(payload, 'PostgreSQL metadata analysis completed successfully.');
    } catch (error) {
      console.error('Error analyzing PostgreSQL database:', error);
      const errorMessage = error.message || 'Unknown error occurred during analysis';
      setAnalysisError(errorMessage);
      showToast('Failed to analyze database', errorMessage, 'error');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleOracleMetadataAnalysis = async () => {
    const host = (connectionDetails.host || connectionDetails.server || '').trim();
    const serviceName = (connectionDetails.serviceName || connectionDetails.database || '').trim();
    const username = (connectionDetails.username || '').trim();
    const password = connectionDetails.password || '';
    const portValue = connectionDetails.port || '1521';
    const port = Number.isNaN(parseInt(portValue, 10)) ? 1521 : parseInt(portValue, 10);
    const targetSchemas = (connectionDetails.targetSchemas || '')
      .split(',')
      .map(schema => schema.trim())
      .filter(Boolean);

    const missingFields = Object.entries({
      host,
      serviceName,
      username,
      password,
    }).filter(([, value]) => !value);

    if (missingFields.length > 0) {
      showToast('Connection details missing', 'Please complete all fields before continuing.', 'error');
      return;
    }

    setIsAnalyzing(true);
    try {
      const requestBody = {
        host,
        service_name: serviceName,
        username,
        password,
        port,
        target_schemas: targetSchemas.length ? targetSchemas : undefined,
        dialect: 'oracle',
        debug: false,
        ollama_url: 'http://localhost:11434',
        ollama_model: 'qwen2.5-coder:14b',
        openai_model: 'gpt-4o-mini',
        batch_size: 10,
        timeout: 300,
      };

      if (useOpenAI && openAIKey) {
        requestBody.openai_api_key = openAIKey;
      }

      if (metadataFilePath) {
        requestBody.metadata_file_path = metadataFilePath;
      }

      const response = await fetch('http://localhost:8000/api/analyze/metadata/oracle', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        let errorMessage = 'Failed to analyze Oracle database';
        try {
          const errorData = await response.json();
          if (errorData?.detail) errorMessage = errorData.detail;
        } catch (_) {
          // ignore
        }
        throw new Error(errorMessage);
      }

      const payload = await response.json();
      applyAnalysisResults(payload, 'Oracle metadata analysis completed successfully.');
    } catch (error) {
      console.error('Error analyzing Oracle database:', error);
      const errorMessage = error.message || 'Unknown error occurred during analysis';
      setAnalysisError(errorMessage);
      showToast('Failed to analyze database', errorMessage, 'error');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleSnowflakeMetadataAnalysis = async () => {
    const account = (connectionDetails.account || '').trim();
    const database = (connectionDetails.database || '').trim();
    const username = (connectionDetails.username || '').trim();
    const password = connectionDetails.password || '';
    const warehouse = (connectionDetails.warehouse || '').trim();
    const role = (connectionDetails.role || '').trim();
    const authenticator = (connectionDetails.authenticator || 'externalbrowser').trim() || 'externalbrowser';

    const missingFields = Object.entries({
      account,
      database,
      username,
    }).filter(([, value]) => !value);

    if (missingFields.length > 0) {
      showToast('Connection details missing', 'Account, database, and username are required.', 'error');
      return;
    }

    setIsAnalyzing(true);
    try {
      const requestBody = {
        account,
        database,
        username,
        password,
        warehouse,
        role,
        authenticator,
        dialect: 'snowflake',
        ollama_url: 'http://localhost:11434',
        ollama_model: 'qwen2.5-coder:14b',
        openai_model: 'gpt-4o-mini',
        batch_size: 10,
        timeout: 300,
      };

      if (useOpenAI && openAIKey) {
        requestBody.openai_api_key = openAIKey;
      }

      const response = await fetch('http://localhost:8000/api/analyze/metadata/snowflake', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        let errorMessage = 'Failed to analyze Snowflake database';
        try {
          const errorData = await response.json();
          if (errorData?.detail) errorMessage = errorData.detail;
        } catch (_) {
          // swallow JSON parse errors
        }
        throw new Error(errorMessage);
      }

      const payload = await response.json();
      applyAnalysisResults(payload, 'Snowflake metadata analysis completed successfully.');
    } catch (error) {
      console.error('Error analyzing Snowflake database:', error);
      const errorMessage = error.message || 'Unknown error occurred during analysis';
      setAnalysisError(errorMessage);
      showToast('Failed to analyze database', errorMessage, 'error');
    } finally {
      setIsAnalyzing(false);
    }
  };


  const handleZoom = (direction) => {
    setZoom(prev => {
      const newZoom = direction === 'in' ? prev * 1.2 : prev / 1.2;
      return Math.max(0.3, Math.min(3, newZoom));
    });
  };

  const handleReset = () => {
    setZoom(0.8);
    setPan({ x: 200, y: 100 });
  };

  const buildSVGString = () => {
    // Check which tab is active and generate SVG accordingly
    if (showProceduresSection) {
      return buildProcedureLineageSVG();
    } else if (showTableDetailsSection) {
      // Table details is a list view, not a graph - return empty or a simple message
      return buildTableDetailsSVG();
    } else {
      // Tabular Components view (default)
      return buildTabularComponentsSVG();
    }
  };

  const buildTabularComponentsSVG = () => {
    if (!lineageData) return '';
    try {
      const columnHeight = 28;
      const tableHeaderHeight = 60;
      const tablePadding = 12;
      const columnSpacing = 4;
      // const tableBottomMargin = 15; // not used in export; keep layout constants minimal

      // Filter tables based on active panel: if on "Tables" panel, exclude views
      let tablesToRender = lineageData.tables;
      if (showTableDetailsSection) {
        // Only show tables (target/source), exclude views (where type is not 'target' or 'source')
        tablesToRender = lineageData.tables.filter(table => 
          table.type === 'target' || table.type === 'source'
        );
      }

      // Filter connections to only include those involving visible tables
      const tableNamesSet = new Set(tablesToRender.map(t => t.name));
      const visibleConnections = lineageData.connections.filter(conn =>
        tableNamesSet.has(conn.sourceTable) &&
        tableNamesSet.has(conn.targetTable) &&
        !hiddenPreviousLevels?.has(conn.sourceTable) &&
        !hiddenPreviousLevels?.has(conn.targetTable) &&
        !hiddenNextLevels?.has(conn.sourceTable) &&
        !hiddenNextLevels?.has(conn.targetTable)
      );

      const allPositions = layoutTablesWithDagre(tablesToRender, visibleConnections);

      // Compute dynamic bounds to avoid clipping in exported SVG
      const margin = 200; // extra padding around content
      const tableXs = allPositions.map(t => t.x);
      const tableYs = allPositions.map(t => t.y);
      const tableMaxX = allPositions.map(t => t.x + t.width);
      const tableMaxY = allPositions.map(t => t.y + t.height);
      const minX = Math.min(...tableXs, 0);
      const minY = Math.min(...tableYs, 0);
      const maxX = Math.max(...tableMaxX, 3000);
      const maxY = Math.max(...tableMaxY, 3000);
      const width = Math.ceil((maxX - minX) + margin * 2);
      const height = Math.ceil((maxY - minY) + margin * 2);
      const bg = theme === 'dark' ? '#0b0f14' : '#f7f7f5';

      const esc = (s) => String(s)
        .replace(/&/g,'&amp;')
        .replace(/</g,'&lt;')
        .replace(/>/g,'&gt;');

      const findColumnIndexForSVG = (table, columnName) => {
        if (!table || !table.columns || !columnName) return -1;
        let idx = table.columns.findIndex(c => c.name === columnName);
        if (idx !== -1) return idx;
        const lower = String(columnName).toLowerCase();
        idx = table.columns.findIndex(c => String(c.name).toLowerCase() === lower);
        if (idx !== -1) return idx;
        const trimQuotes = (str) => {
          let out = String(str);
          if (out.startsWith('`') || out.startsWith('"') || out.startsWith('[')) out = out.slice(1);
          if (out.endsWith('`') || out.endsWith('"') || out.endsWith(']')) out = out.slice(0, -1);
          return out;
        };
        const trimmed = trimQuotes(columnName);
        if (trimmed !== columnName) {
          return table.columns.findIndex(c => trimQuotes(c.name) === trimmed);
        }
        return -1;
      };

      const parts = [];
      parts.push('<?xml version="1.0" encoding="UTF-8"?>');
      parts.push(`<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`);
      parts.push(`<defs>
        <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
          <polygon points="0 0, 10 3, 0 6" fill="#3b82f6" />
        </marker>
      </defs>`);
      parts.push(`<rect x="0" y="0" width="${width}" height="${height}" fill="${bg}" />`);
      // Shift content so everything sits well within the viewBox
      const offsetX = margin - minX + pan.x;
      const offsetY = margin - minY + pan.y;
      parts.push(`<g transform="translate(${offsetX}, ${offsetY}) scale(${zoom})">`);

      // For export: always include all column-level connections (reverted behavior)
      const columnConnectionsToRender = visibleConnections;

      // Connections
      visibleConnections.forEach((conn) => {
        const sourceTable = allPositions.find(t => t.name === conn.sourceTable);
        const targetTable = allPositions.find(t => t.name === conn.targetTable);
        if (!sourceTable || !targetTable) return;

        const tableSourceX = sourceTable.x + sourceTable.width + 8;
        const tableSourceY = sourceTable.y + tableHeaderHeight / 2;
        const tableTargetX = targetTable.x - 8;
        const tableTargetY = targetTable.y + tableHeaderHeight / 2;
        const c1x = tableSourceX + (tableTargetX - tableSourceX) * 0.5;
        const c2x = tableTargetX - (tableTargetX - tableSourceX) * 0.5;
        const tableStroke = theme === 'dark' ? '#ffffff' : '#000000';
        parts.push(`<path d="M ${tableSourceX} ${tableSourceY} C ${c1x} ${tableSourceY}, ${c2x} ${tableTargetY}, ${tableTargetX} ${tableTargetY}" fill="none" stroke="${tableStroke}" stroke-width="2" opacity="0.8" marker-end="url(#arrowhead)" />`);

        const sourceExpanded = expandedTables.has(sourceTable.name);
        const targetExpanded = expandedTables.has(targetTable.name);
        const isInColumnSet = columnConnectionsToRender.some(h => h.sourceTable === conn.sourceTable && h.sourceColumn === conn.sourceColumn && h.targetTable === conn.targetTable && h.targetColumn === conn.targetColumn);
        if (isInColumnSet && sourceExpanded && targetExpanded) {
          const sIdx = findColumnIndexForSVG(sourceTable, conn.sourceColumn);
          const tIdx = findColumnIndexForSVG(targetTable, conn.targetColumn);
          if (sIdx !== -1 && tIdx !== -1) {
            const sourceX = sourceTable.x + sourceTable.width;
            const sourceY = sourceTable.y + tableHeaderHeight + tablePadding + (sIdx * (columnHeight + columnSpacing)) + (columnHeight / 2);
            const targetX = targetTable.x;
            const targetY = targetTable.y + tableHeaderHeight + tablePadding + (tIdx * (columnHeight + columnSpacing)) + (columnHeight / 2);
            const cp1x = sourceX + (targetX - sourceX) * 0.5;
            const cp2x = targetX - (targetX - sourceX) * 0.5;
            const color = getTransformationColor(conn.transformationType);
            parts.push(`<path d="M ${sourceX} ${sourceY} C ${cp1x} ${sourceY}, ${cp2x} ${targetY}, ${targetX} ${targetY}" fill="none" stroke="${color}" stroke-width="2.5" opacity="1" marker-end="url(#arrowhead)" />`);
          }
        }
      });

      // Tables
        allPositions.forEach((table) => {
        const isExpanded = expandedTables.has(table.name);
        const isSource = table.type === 'source';
        const isTarget = table.type === 'target';
        const headerFill = isTarget ? '#2563eb' : (isSource ? '#4b5563' : '#10b981');
        const bodyFill = theme === 'dark' ? '#1f2937' : '#ffffff';
        const border = '#e5e7eb';

        parts.push(`<g>`);
        parts.push(`<rect x="${table.x}" y="${table.y}" width="${table.width}" height="${table.height}" rx="8" ry="8" fill="${bodyFill}" stroke="${border}" stroke-width="2" />`);
        parts.push(`<rect x="${table.x}" y="${table.y}" width="${table.width}" height="${tableHeaderHeight}" rx="8" ry="8" fill="${headerFill}" />`);
        parts.push(`<text x="${table.x + 40}" y="${table.y + 22}" fill="#ffffff" font-size="11" font-family="monospace" opacity="0.9">${esc(table.schema)}</text>`);
        parts.push(`<text x="${table.x + 40}" y="${table.y + 42}" fill="#ffffff" font-size="15" font-weight="700" font-family="sans-serif">${esc(table.tableName)}</text>`);
        const badge = isTarget ? 'Target' : (isSource ? 'Source' : 'Table');
        parts.push(`<rect x="${table.x + table.width - 80}" y="${table.y + 14}" width="66" height="22" rx="6" ry="6" fill="rgba(255,255,255,0.2)" stroke="rgba(255,255,255,0.1)" />`);
        parts.push(`<text x="${table.x + table.width - 47}" y="${table.y + 30}" fill="#ffffff" font-size="11" font-weight="600" text-anchor="middle" font-family="sans-serif">${badge}</text>`);

          if (isExpanded && table.columns && table.columns.length > 0) {
          const colStartY = table.y + tableHeaderHeight + tablePadding;
          table.columns.forEach((col, idx) => {
            const y = colStartY + idx * (columnHeight + columnSpacing);
            const hasConn = lineageData.connections.some(c =>
              (c.sourceTable === table.name && c.sourceColumn === col.name) ||
              (c.targetTable === table.name && c.targetColumn === col.name)
            );
            const rowFill = hasConn ? 'rgba(59,130,246,0.35)' : (theme === 'dark' ? 'rgba(55,65,81,0.5)' : 'rgba(243,244,246,0.9)');
            parts.push(`<rect x="${table.x + tablePadding}" y="${y}" width="${table.width - 2 * tablePadding}" height="${columnHeight}" rx="4" ry="4" fill="${rowFill}" />`);
            parts.push(`<circle cx="${table.x + tablePadding + 12}" cy="${y + columnHeight / 2}" r="4" fill="${hasConn ? '#60a5fa' : '#6b7280'}" />`);
            const textColor = theme === 'dark' ? '#e5e7eb' : '#111827';
            parts.push(`<text x="${table.x + tablePadding + 24}" y="${y + 18}" fill="${textColor}" font-size="14" font-family="monospace">${esc(col.name)}</text>`);
          });
        }
        parts.push('</g>');
      });

      parts.push('</g>');
      parts.push('</svg>');
      const svgString = parts.join('');
      return svgString;
    } catch (e) {
      console.error('Failed to print SVG:', e);
      return '';
    }
  };

  const buildProcedureLineageSVG = () => {
    if (!procedureLineageData || !selectedProcedure) {
      return buildEmptySVG('No Executable Component selected');
    }
    try {
      const columnHeight = 28;
      const nodeHeaderHeight = 60;
      const nodePadding = 12;
      const columnSpacing = 4;
      const nodeWidth = 320;

      // Get visible nodes and connections for selected procedure
      const relatedNodes = new Set([selectedProcedure]);
      procedureLineageData.connections.forEach(conn => {
        if (conn.source === selectedProcedure || conn.target === selectedProcedure) {
          relatedNodes.add(conn.source);
          relatedNodes.add(conn.target);
        }
      });

      // Get the raw procedure data to extract column_lineage
      const selectedIsFunction = !!procedureLineage?.functions?.[selectedProcedure];
      const selectedIsTrigger = !!procedureLineage?.triggers?.[selectedProcedure];
      const selectedRaw = selectedIsTrigger
        ? procedureLineage?.triggers?.[selectedProcedure]
        : (selectedIsFunction 
          ? procedureLineage?.functions?.[selectedProcedure]
          : procedureLineage?.procedures?.[selectedProcedure]);

      // Will be updated after processing column_lineage
      let visibleNodes = [];
      
      // Include both table-level and column-level connections for SVG export
      const visibleConnections = procedureLineageData.connections.filter(conn => 
        relatedNodes.has(conn.source) && relatedNodes.has(conn.target)
      );
      
      // Separate table-level and column-level connections
      const tableLevelConnections = visibleConnections.filter(conn =>
        conn.type !== 'column_of' && conn.type !== 'column_read' && 
        conn.type !== 'column_write' && conn.type !== 'column_update'
      );
      const columnLevelConnections = visibleConnections.filter(conn =>
        conn.type === 'column_read' || conn.type === 'column_write' || conn.type === 'column_update'
      );
      
      // Also create column-to-column connections from column_lineage for table-to-table mappings
      const columnLineageConnections = [];
      if (selectedRaw?.column_lineage) {
        selectedRaw.column_lineage.forEach(lineage => {
          const targetCol = lineage.target_column;
          if (!targetCol) return;
          
          // Parse target column (format: table.column)
          const targetParts = targetCol.split('.');
          if (targetParts.length < 2) return;
          const targetTableName = targetParts.slice(0, -1).join('.');
          const targetColName = targetParts[targetParts.length - 1];
          
          // Add target table to related nodes if not already there
          relatedNodes.add(targetTableName);
          
          // Process source columns
          (lineage.sources || []).forEach(sourceCol => {
            let sourceTableName, sourceColName;
            
            if (typeof sourceCol === 'string') {
              // Format: table.column
              const parts = sourceCol.split('.');
              if (parts.length < 2) return;
              sourceTableName = parts.slice(0, -1).join('.');
              sourceColName = parts[parts.length - 1];
            } else if (sourceCol && sourceCol.table_list && sourceCol.column) {
              // Format: { table_list: "table", column: "column" }
              sourceTableName = sourceCol.table_list;
              sourceColName = sourceCol.column;
            } else {
              return;
            }
            
            // Add source table to related nodes if not already there
            relatedNodes.add(sourceTableName);
            
            // Create a connection from source table.column to target table.column
            columnLineageConnections.push({
              source: `${sourceTableName}.${sourceColName}`,
              target: `${targetTableName}.${targetColName}`,
              type: 'column_lineage',
              sourceTable: sourceTableName,
              sourceColumn: sourceColName,
              targetTable: targetTableName,
              targetColumn: targetColName
            });
          });
        });
      }
      
      // Update visibleNodes to include all tables from column_lineage
      visibleNodes = procedureLineageData.nodes.filter(n => 
        relatedNodes.has(n.name) && n.type !== 'column'
      );
      
      // Ensure all tables from column_lineage are included as nodes
      const allTableNames = new Set(visibleNodes.filter(n => n.type === 'table').map(n => n.name));
      columnLineageConnections.forEach(conn => {
        if (!allTableNames.has(conn.sourceTable)) {
          const [schema, name] = conn.sourceTable.includes('.') 
            ? conn.sourceTable.split('.') 
            : ['default', conn.sourceTable];
          visibleNodes.push({
            name: conn.sourceTable,
            schema: schema,
            nodeName: name,
            type: 'table',
            file: 'External'
          });
          allTableNames.add(conn.sourceTable);
        }
        if (!allTableNames.has(conn.targetTable)) {
          const [schema, name] = conn.targetTable.includes('.') 
            ? conn.targetTable.split('.') 
            : ['default', conn.targetTable];
          visibleNodes.push({
            name: conn.targetTable,
            schema: schema,
            nodeName: name,
            type: 'table',
            file: 'External'
          });
          allTableNames.add(conn.targetTable);
        }
      });

      if (visibleNodes.length === 0) {
        return buildEmptySVG('No data available for selected Executable Component');
      }

      // Create dagre graph for layout
      const g = new dagre.graphlib.Graph();
      g.setGraph({ 
        rankdir: 'LR', 
        ranksep: 300, 
        nodesep: 100,
        edgesep: 50,
        marginx: 50,
        marginy: 50
      });
      g.setDefaultEdgeLabel(() => ({}));

      // Helper to get table columns from lineageData if not in node
      const getTableColumns = (tableName) => {
        if (!lineageData?.tables) return null;
        const table = lineageData.tables.find(t => t.name === tableName);
        return table?.columns || null;
      };
      
      // Add nodes - for SVG export, always expand tables and the selected executable component
      visibleNodes.forEach(node => {
        const isTable = node.type === 'table';
        const isSelectedExecutable = node.name === selectedProcedure;
        // Always expand tables and the selected procedure/function/trigger
        const shouldExpand = isTable || isSelectedExecutable ? true : expandedProcedures.has(node.name);
        
        // For tables, ensure we have columns (get from lineageData if needed)
        let columns = node.columns;
        if (isTable && (!columns || columns.length === 0)) {
          const tableCols = getTableColumns(node.name);
          if (tableCols) {
            columns = tableCols.map(col => typeof col === 'string' ? { name: col } : col);
          }
        }
        
        const height = shouldExpand && columns && columns.length > 0
          ? nodeHeaderHeight + nodePadding + (columns.length * (columnHeight + columnSpacing)) + nodePadding
          : nodeHeaderHeight;
        g.setNode(node.name, { 
          label: node.name, 
          width: nodeWidth, 
          height: height 
        });
      });

      // Add edges (only table-level connections for dagre layout)
      tableLevelConnections.forEach(conn => {
        if (g.hasNode(conn.source) && g.hasNode(conn.target)) {
          g.setEdge(conn.source, conn.target);
        }
      });

      dagre.layout(g);

      // Helper to get table columns from lineageData if not in node
      const getTableColumnsForNode = (node) => {
        if (node.type === 'table') {
          if (node.columns && node.columns.length > 0) return node.columns;
          const tableCols = getTableColumns(node.name);
          if (tableCols) {
            return tableCols.map(col => typeof col === 'string' ? { name: col } : col);
          }
        }
        return node.columns || [];
      };
      
      // Get positions - recalculate height to ensure tables and selected executable are expanded
      const allPositions = visibleNodes.map(node => {
        const dagreNode = g.node(node.name);
        if (!dagreNode) return null;
        // Recalculate height to ensure tables and selected executable are always expanded
        const isTable = node.type === 'table';
        const isSelectedExecutable = node.name === selectedProcedure;
        const shouldExpand = isTable || isSelectedExecutable ? true : expandedProcedures.has(node.name);
        
        // Get columns (from node or lineageData for tables)
        const columns = getTableColumnsForNode(node);
        const actualHeight = shouldExpand && columns && columns.length > 0
          ? nodeHeaderHeight + nodePadding + (columns.length * (columnHeight + columnSpacing)) + nodePadding
          : nodeHeaderHeight;
        
        return {
          ...node,
          columns: columns, // Ensure columns are included
          x: dagreNode.x - dagreNode.width / 2,
          y: dagreNode.y - dagreNode.height / 2,
          width: dagreNode.width,
          height: actualHeight // Use recalculated height
        };
      }).filter(Boolean);

      // Calculate bounds
      const margin = 200;
      const nodeXs = allPositions.map(n => n.x);
      const nodeYs = allPositions.map(n => n.y);
      const nodeMaxX = allPositions.map(n => n.x + n.width);
      const nodeMaxY = allPositions.map(n => n.y + n.height);
      const minX = Math.min(...nodeXs, 0);
      const minY = Math.min(...nodeYs, 0);
      const maxX = Math.max(...nodeMaxX, 3000);
      const maxY = Math.max(...nodeMaxY, 3000);
      const width = Math.ceil((maxX - minX) + margin * 2);
      const height = Math.ceil((maxY - minY) + margin * 2);
      const bg = theme === 'dark' ? '#0b0f14' : '#f7f7f5';

      const esc = (s) => String(s)
        .replace(/&/g,'&amp;')
        .replace(/</g,'&lt;')
        .replace(/>/g,'&gt;');

      const parts = [];
      parts.push('<?xml version="1.0" encoding="UTF-8"?>');
      parts.push(`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`);
      parts.push(`<defs>
        <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
          <polygon points="0 0, 10 3, 0 6" fill="#3b82f6" />
        </marker>
      </defs>`);
      parts.push(`<rect x="0" y="0" width="${width}" height="${height}" fill="${bg}" />`);
      const offsetX = margin - minX + pan.x;
      const offsetY = margin - minY + pan.y;
      parts.push(`<g transform="translate(${offsetX}, ${offsetY}) scale(${zoom})">`);

      // Helper to find column index in table
      const findColumnIndexForSVG = (table, columnName) => {
        if (!table || !table.columns || !columnName) return -1;
        const colName = typeof columnName === 'string' ? columnName : columnName.name || columnName.column;
        let idx = table.columns.findIndex(c => {
          const cName = typeof c === 'string' ? c : c.name;
          return cName === colName;
        });
        if (idx !== -1) return idx;
        const lower = String(colName).toLowerCase();
        idx = table.columns.findIndex(c => {
          const cName = typeof c === 'string' ? c : c.name;
          return String(cName).toLowerCase() === lower;
        });
        return idx;
      };
      
      // Draw table-level connections
      tableLevelConnections.forEach(conn => {
        const sourceNode = allPositions.find(n => n.name === conn.source);
        const targetNode = allPositions.find(n => n.name === conn.target);
        if (!sourceNode || !targetNode) return;

        const sourceX = sourceNode.x + sourceNode.width + 8;
        const sourceY = sourceNode.y + nodeHeaderHeight / 2;
        const targetX = targetNode.x - 8;
        const targetY = targetNode.y + nodeHeaderHeight / 2;
        const c1x = sourceX + (targetX - sourceX) * 0.5;
        const c2x = targetX - (targetX - sourceX) * 0.5;
        const stroke = theme === 'dark' ? '#ffffff' : '#000000';
        parts.push(`<path d="M ${sourceX} ${sourceY} C ${c1x} ${sourceY}, ${c2x} ${targetY}, ${targetX} ${targetY}" fill="none" stroke="${stroke}" stroke-width="2" opacity="0.8" marker-end="url(#arrowhead)" />`);
      });
      
      // Draw column-to-column connections from column_lineage (table-to-table)
      columnLineageConnections.forEach(conn => {
        const sourceNode = allPositions.find(n => n.name === conn.sourceTable);
        const targetNode = allPositions.find(n => n.name === conn.targetTable);
        if (!sourceNode || !targetNode || sourceNode.type !== 'table' || targetNode.type !== 'table') return;
        if (!sourceNode.columns || !targetNode.columns || sourceNode.columns.length === 0 || targetNode.columns.length === 0) return;
        
        const sIdx = findColumnIndexForSVG(sourceNode, conn.sourceColumn);
        const tIdx = findColumnIndexForSVG(targetNode, conn.targetColumn);
        
        if (sIdx !== -1 && tIdx !== -1) {
          const sourceX = sourceNode.x + sourceNode.width;
          const sourceY = sourceNode.y + nodeHeaderHeight + nodePadding + (sIdx * (columnHeight + columnSpacing)) + (columnHeight / 2);
          const targetX = targetNode.x;
          const targetY = targetNode.y + nodeHeaderHeight + nodePadding + (tIdx * (columnHeight + columnSpacing)) + (columnHeight / 2);
          const cp1x = sourceX + (targetX - sourceX) * 0.5;
          const cp2x = targetX - (targetX - sourceX) * 0.5;
          
          // Use blue for column lineage connections
          const color = '#3b82f6';
          parts.push(`<path d="M ${sourceX} ${sourceY} C ${cp1x} ${sourceY}, ${cp2x} ${targetY}, ${targetX} ${targetY}" fill="none" stroke="${color}" stroke-width="2.5" opacity="1" marker-end="url(#arrowhead)" />`);
        }
      });
      
      // Draw column-level connections (similar to tabular components view)
      columnLevelConnections.forEach(conn => {
        let sourceNode, targetNode, sourceColName, targetColName;
        
        if (conn.type === 'column_read') {
          // source is table.column, target is procedure
          const sourceParts = conn.source.split('.');
          if (sourceParts.length < 2) return;
          const tableName = sourceParts.slice(0, -1).join('.');
          sourceColName = sourceParts[sourceParts.length - 1];
          sourceNode = allPositions.find(n => n.name === tableName);
          targetNode = allPositions.find(n => n.name === conn.target);
        } else if (conn.type === 'column_write' || conn.type === 'column_update') {
          // source is procedure, target is table.column
          const targetParts = conn.target.split('.');
          if (targetParts.length < 2) return;
          const tableName = targetParts.slice(0, -1).join('.');
          targetColName = targetParts[targetParts.length - 1];
          sourceNode = allPositions.find(n => n.name === conn.source);
          targetNode = allPositions.find(n => n.name === tableName);
        } else {
          return;
        }
        
        if (!sourceNode || !targetNode) return;
        
        // Only draw if both nodes are tables with columns and we found column names
        if (sourceNode.type === 'table' && targetNode.type === 'table' && 
            sourceColName && targetColName &&
            sourceNode.columns && sourceNode.columns.length > 0 &&
            targetNode.columns && targetNode.columns.length > 0) {
          const sIdx = findColumnIndexForSVG(sourceNode, sourceColName);
          const tIdx = findColumnIndexForSVG(targetNode, targetColName);
          
          if (sIdx !== -1 && tIdx !== -1) {
            const sourceX = sourceNode.x + sourceNode.width;
            const sourceY = sourceNode.y + nodeHeaderHeight + nodePadding + (sIdx * (columnHeight + columnSpacing)) + (columnHeight / 2);
            const targetX = targetNode.x;
            const targetY = targetNode.y + nodeHeaderHeight + nodePadding + (tIdx * (columnHeight + columnSpacing)) + (columnHeight / 2);
            const cp1x = sourceX + (targetX - sourceX) * 0.5;
            const cp2x = targetX - (targetX - sourceX) * 0.5;
            
            // Determine connection color based on type
            let color = '#3b82f6'; // default blue
            if (conn.type === 'column_read') color = '#10b981'; // green for reads
            else if (conn.type === 'column_write') color = '#ef4444'; // red for writes
            else if (conn.type === 'column_update') color = '#f59e0b'; // orange for updates
            
            parts.push(`<path d="M ${sourceX} ${sourceY} C ${cp1x} ${sourceY}, ${cp2x} ${targetY}, ${targetX} ${targetY}" fill="none" stroke="${color}" stroke-width="2.5" opacity="1" marker-end="url(#arrowhead)" />`);
          }
        } else if ((sourceNode.type === 'table' && targetNode.type !== 'table') || 
                   (sourceNode.type !== 'table' && targetNode.type === 'table')) {
          // Connection between table column and procedure/function/trigger
          const tableNode = sourceNode.type === 'table' ? sourceNode : targetNode;
          const colName = sourceNode.type === 'table' ? sourceColName : targetColName;
          const procNode = sourceNode.type === 'table' ? targetNode : sourceNode;
          
          if (tableNode.columns && tableNode.columns.length > 0 && colName) {
            const colIdx = findColumnIndexForSVG(tableNode, colName);
            if (colIdx !== -1) {
              const tableX = tableNode.x + (sourceNode.type === 'table' ? tableNode.width : -8);
              const tableY = tableNode.y + nodeHeaderHeight + nodePadding + (colIdx * (columnHeight + columnSpacing)) + (columnHeight / 2);
              const procX = procNode.x + (sourceNode.type === 'table' ? -8 : procNode.width + 8);
              const procY = procNode.y + nodeHeaderHeight / 2;
              const cp1x = tableX + (procX - tableX) * 0.5;
              const cp2x = procX - (procX - tableX) * 0.5;
              
              let color = '#3b82f6';
              if (conn.type === 'column_read') color = '#10b981';
              else if (conn.type === 'column_write') color = '#ef4444';
              else if (conn.type === 'column_update') color = '#f59e0b';
              
              parts.push(`<path d="M ${tableX} ${tableY} C ${cp1x} ${tableY}, ${cp2x} ${procY}, ${procX} ${procY}" fill="none" stroke="${color}" stroke-width="2.5" opacity="1" marker-end="url(#arrowhead)" />`);
            }
          }
        }
      });

      // Draw nodes
      allPositions.forEach(node => {
        // For SVG export: always expand tables and the selected executable component
        const isTable = node.type === 'table';
        const isSelectedExecutable = node.name === selectedProcedure;
        const isExpanded = isTable || isSelectedExecutable ? true : expandedProcedures.has(node.name);
        const isProcedure = node.type === 'procedure';
        const isTrigger = node.type === 'trigger';
        const headerFill = isTable 
          ? (node.type === 'target' ? '#2563eb' : (node.type === 'source' ? '#4b5563' : '#10b981')) 
          : (isTrigger ? '#dc2626' : (isProcedure ? '#059669' : '#7c3aed'));
        const bodyFill = theme === 'dark' ? '#1f2937' : '#ffffff';
        const border = '#e5e7eb';

        parts.push(`<g>`);
        parts.push(`<rect x="${node.x}" y="${node.y}" width="${node.width}" height="${node.height}" rx="8" ry="8" fill="${bodyFill}" stroke="${border}" stroke-width="2" />`);
        parts.push(`<rect x="${node.x}" y="${node.y}" width="${node.width}" height="${nodeHeaderHeight}" rx="8" ry="8" fill="${headerFill}" />`);
        parts.push(`<text x="${node.x + 40}" y="${node.y + 35}" fill="#ffffff" font-size="15" font-weight="700" font-family="sans-serif">${esc(node.name)}</text>`);
        const badge = isTable 
          ? (node.type === 'target' ? 'TARGET' : (node.type === 'source' ? 'SOURCE' : 'TABLE')) 
          : (isTrigger ? 'TRIG' : (isProcedure ? 'PROC' : 'FUNC'));
        parts.push(`<rect x="${node.x + node.width - 70}" y="${node.y + 14}" width="56" height="22" rx="6" ry="6" fill="rgba(255,255,255,0.2)" />`);
        parts.push(`<text x="${node.x + node.width - 42}" y="${node.y + 30}" fill="#ffffff" font-size="11" font-weight="600" text-anchor="middle">${badge}</text>`);

        if (isExpanded && node.columns && node.columns.length > 0) {
          const colStartY = node.y + nodeHeaderHeight + nodePadding;
          node.columns.forEach((col, idx) => {
            const y = colStartY + idx * (columnHeight + columnSpacing);
            const colName = typeof col === 'string' ? col : (col.name || col.column || '');
            const hasConn = columnLevelConnections.some(c => {
              if (c.type === 'column_read') {
                const parts = c.source.split('.');
                return parts.length > 1 && parts[parts.length - 1] === colName && parts.slice(0, -1).join('.') === node.name;
              } else if (c.type === 'column_write' || c.type === 'column_update') {
                const parts = c.target.split('.');
                return parts.length > 1 && parts[parts.length - 1] === colName && parts.slice(0, -1).join('.') === node.name;
              }
              return false;
            }) || columnLineageConnections.some(c => {
              return (c.sourceTable === node.name && c.sourceColumn === colName) ||
                     (c.targetTable === node.name && c.targetColumn === colName);
            });
            const rowFill = hasConn 
              ? 'rgba(59,130,246,0.35)' 
              : (theme === 'dark' ? 'rgba(55,65,81,0.5)' : 'rgba(243,244,246,0.9)');
            parts.push(`<rect x="${node.x + nodePadding}" y="${y}" width="${node.width - 2 * nodePadding}" height="${columnHeight}" rx="4" ry="4" fill="${rowFill}" />`);
            parts.push(`<circle cx="${node.x + nodePadding + 12}" cy="${y + columnHeight / 2}" r="4" fill="${hasConn ? '#60a5fa' : '#6b7280'}" />`);
            const textColor = theme === 'dark' ? '#e5e7eb' : '#111827';
            parts.push(`<text x="${node.x + nodePadding + 24}" y="${y + 18}" fill="${textColor}" font-size="14" font-family="monospace">${esc(colName)}</text>`);
          });
        }
        parts.push('</g>');
      });

      parts.push('</g>');
      parts.push('</svg>');
      return parts.join('');
    } catch (e) {
      console.error('Failed to build procedure lineage SVG:', e);
      return buildEmptySVG('Error generating SVG');
    }
  };

  const buildTableDetailsSVG = () => {
    if (!lineageData || !lineageData.tables) {
      return buildEmptySVG('No Tabular Component data available');
    }
    try {
      const columnHeight = 28;
      const tableHeaderHeight = 60;
      const tablePadding = 12;
      const columnSpacing = 4;
      const tableWidth = 320;
      const tableSpacing = 50;
      const margin = 50;

      // Filter to only tables with columns
      const tablesToRender = lineageData.tables.filter(table => 
        table.columns && table.columns.length > 0
      );

      if (tablesToRender.length === 0) {
        return buildEmptySVG('No tables with columns available');
      }

      // Calculate layout: simple grid/list - 2 columns
      const colsPerRow = 2;
      const titleHeight = 80; // Space for title
      
      // First pass: calculate all table heights
      const tableHeights = tablesToRender.map(table => {
        return tableHeaderHeight + tablePadding + 
          (table.columns.length * (columnHeight + columnSpacing)) + tablePadding;
      });
      
      // Calculate row positions based on maximum height in each row
      const allPositions = [];
      let currentY = margin + titleHeight;
      
      for (let idx = 0; idx < tablesToRender.length; idx++) {
        const row = Math.floor(idx / colsPerRow);
        const col = idx % colsPerRow;
        const tableHeight = tableHeights[idx];
        
        // If this is the first column of a new row, calculate max height of previous row
        if (col === 0 && row > 0) {
          // Find max height in previous row
          const prevRowStart = (row - 1) * colsPerRow;
          const prevRowEnd = Math.min(prevRowStart + colsPerRow, tablesToRender.length);
          const maxHeightInPrevRow = Math.max(...tableHeights.slice(prevRowStart, prevRowEnd));
          currentY += maxHeightInPrevRow + tableSpacing;
        }
        
        allPositions.push({
          ...tablesToRender[idx],
          x: margin + col * (tableWidth + tableSpacing),
          y: currentY,
          width: tableWidth,
          height: tableHeight
        });
      }

      // Calculate bounds
      const maxX = Math.max(...allPositions.map(t => t.x + t.width)) + margin;
      const maxY = Math.max(...allPositions.map(t => t.y + t.height)) + margin;
      const width = maxX;
      const height = maxY;
      const bg = theme === 'dark' ? '#0b0f14' : '#f7f7f5';

      const esc = (s) => String(s)
        .replace(/&/g,'&amp;')
        .replace(/</g,'&lt;')
        .replace(/>/g,'&gt;');

      const parts = [];
      parts.push('<?xml version="1.0" encoding="UTF-8"?>');
      parts.push(`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`);
      parts.push(`<rect x="0" y="0" width="${width}" height="${height}" fill="${bg}" />`);
      
      // Title
      parts.push(`<text x="${width/2}" y="30" fill="${theme === 'dark' ? '#e5e7eb' : '#111827'}" font-size="24" font-weight="700" font-family="sans-serif" text-anchor="middle">Tabular Component List</text>`);
      parts.push(`<text x="${width/2}" y="55" fill="${theme === 'dark' ? '#9ca3af' : '#6b7280'}" font-size="14" font-family="sans-serif" text-anchor="middle">${tablesToRender.length} tables</text>`);

      // Draw tables
      allPositions.forEach((table) => {
        const isSource = table.type === 'source';
        const isTarget = table.type === 'target';
        const headerFill = isTarget ? '#2563eb' : (isSource ? '#4b5563' : '#10b981');
        const bodyFill = theme === 'dark' ? '#1f2937' : '#ffffff';
        const border = '#e5e7eb';

        parts.push(`<g>`);
        parts.push(`<rect x="${table.x}" y="${table.y}" width="${table.width}" height="${table.height}" rx="8" ry="8" fill="${bodyFill}" stroke="${border}" stroke-width="2" />`);
        parts.push(`<rect x="${table.x}" y="${table.y}" width="${table.width}" height="${tableHeaderHeight}" rx="8" ry="8" fill="${headerFill}" />`);
        parts.push(`<text x="${table.x + 40}" y="${table.y + 22}" fill="#ffffff" font-size="11" font-family="monospace" opacity="0.9">${esc(table.schema || '')}</text>`);
        parts.push(`<text x="${table.x + 40}" y="${table.y + 42}" fill="#ffffff" font-size="15" font-weight="700" font-family="sans-serif">${esc(table.tableName)}</text>`);
        const badge = isTarget ? 'Target' : (isSource ? 'Source' : 'Table');
        parts.push(`<rect x="${table.x + table.width - 80}" y="${table.y + 14}" width="66" height="22" rx="6" ry="6" fill="rgba(255,255,255,0.2)" stroke="rgba(255,255,255,0.1)" />`);
        parts.push(`<text x="${table.x + table.width - 47}" y="${table.y + 30}" fill="#ffffff" font-size="11" font-weight="600" text-anchor="middle" font-family="sans-serif">${badge}</text>`);

        // Always show all columns (expanded)
        if (table.columns && table.columns.length > 0) {
          const colStartY = table.y + tableHeaderHeight + tablePadding;
          table.columns.forEach((col, idx) => {
            const y = colStartY + idx * (columnHeight + columnSpacing);
            const rowFill = theme === 'dark' ? 'rgba(55,65,81,0.5)' : 'rgba(243,244,246,0.9)';
            parts.push(`<rect x="${table.x + tablePadding}" y="${y}" width="${table.width - 2 * tablePadding}" height="${columnHeight}" rx="4" ry="4" fill="${rowFill}" />`);
            parts.push(`<circle cx="${table.x + tablePadding + 12}" cy="${y + columnHeight / 2}" r="4" fill="#6b7280" />`);
            const textColor = theme === 'dark' ? '#e5e7eb' : '#111827';
            parts.push(`<text x="${table.x + tablePadding + 24}" y="${y + 18}" fill="${textColor}" font-size="14" font-family="monospace">${esc(col.name)}</text>`);
          });
        }
        parts.push('</g>');
      });

      parts.push('</svg>');
      return parts.join('');
    } catch (e) {
      console.error('Failed to build table details SVG:', e);
      return buildEmptySVG('Error generating table list SVG');
    }
  };

  const buildEmptySVG = (message) => {
    const width = 800;
    const height = 400;
    const bg = theme === 'dark' ? '#0b0f14' : '#f7f7f5';
    const textColor = theme === 'dark' ? '#9ca3af' : '#6b7280';
    
    return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <rect x="0" y="0" width="${width}" height="${height}" fill="${bg}" />
  <text x="${width/2}" y="${height/2}" fill="${textColor}" font-size="18" font-family="sans-serif" text-anchor="middle">${message}</text>
</svg>`;
  };

  const handlePreviewSVG = () => {
    const svg = buildSVGString();
    if (!svg) return;
    setPreviewSVG(svg);
    setIsPreviewOpen(true);
  };

  const handleExportSVG = () => {
    const svgString = buildSVGString();
    if (!svgString) return;
    const blob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    // Set filename based on active tab
    let filename = 'lineage_graph.svg';
    if (showProceduresSection) {
      filename = selectedProcedure 
        ? `executable_component_${selectedProcedure.replace(/[^a-zA-Z0-9]/g, '_')}.svg`
        : 'executable_components_lineage.svg';
    } else if (showTableDetailsSection) {
      filename = 'tabular_component_list.svg';
    } else {
      filename = 'tabular_components_lineage.svg';
    }
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleMouseDown = (e) => {
    // Allow dragging on canvas background, SVG, or empty areas
    if (e.target.classList.contains('canvas-bg') || 
        e.target.tagName === 'svg' || 
        e.target === canvasRef.current ||
        e.target.classList.contains('canvas-container')) {
      setIsDragging(true);
      setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
      e.preventDefault();
    }
  };

  useEffect(() => {
    if (isDragging) {
      const handleMouseMove = (e) => {
        setPan({
          x: e.clientX - dragStart.x,
          y: e.clientY - dragStart.y
        });
      };

      const handleMouseUp = () => {
        setIsDragging(false);
      };

      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      
      return () => {
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isDragging, dragStart]);

  const toggleTable = (tableName) => {
    setExpandedTables(prev => {
      const next = new Set(prev);
      if (next.has(tableName)) {
        next.delete(tableName);
      } else {
        next.add(tableName);
      }
      return next;
    });
  };

  const ensureTablesExpanded = (tableNames) => {
    if (!tableNames || tableNames.length === 0) return;
    setExpandedTables(prev => {
      const next = new Set(prev);
      tableNames.forEach(name => next.add(name));
      return next;
    });
  };

  const ensureTablesCollapsed = (tableNames) => {
    if (!tableNames || tableNames.length === 0) return;
    setExpandedTables(prev => {
      const next = new Set(prev);
      tableNames.forEach(name => next.delete(name));
      return next;
    });
  };

  const expandTableLevel = (tableName, side) => {
    if (!lineageData) return;
    
    const connections = lineageData.connections;
    
    if (side === 'left') {
      // Left side: expand previous level (tables that feed into this table)
      const previousTables = connections
        .filter(conn => conn.targetTable === tableName)
        .map(conn => conn.sourceTable);
      
      // In focus mode, add to focused connections
      if (focusedTable && focusedTableConnections.size > 0) {
        setFocusedTableConnections(prev => {
          const next = new Set(prev);
          previousTables.forEach(table => next.add(table));
          return next;
        });
      } else {
        // Normal mode: remove from hidden levels (show them)
        setHiddenPreviousLevels(prev => {
          const next = new Set(prev);
          previousTables.forEach(table => next.delete(table));
          return next;
        });
      }
    } else if (side === 'right') {
      // Right side: expand next level (tables that this table feeds into)
      const nextTables = connections
        .filter(conn => conn.sourceTable === tableName)
        .map(conn => conn.targetTable);
      
      // In focus mode, add to focused connections
      if (focusedTable && focusedTableConnections.size > 0) {
        setFocusedTableConnections(prev => {
          const next = new Set(prev);
          nextTables.forEach(table => next.add(table));
          return next;
        });
      } else {
        // Normal mode: remove from hidden levels (show them)
        setHiddenNextLevels(prev => {
          const next = new Set(prev);
          nextTables.forEach(table => next.delete(table));
          return next;
        });
      }
    }
  };

  const focusOnTable = (tableName) => {
    if (!lineageData) return;
    
    if (focusedTable === tableName) {
      // If clicking the same table, unfocus
      setFocusedTable(null);
      setFocusedTableConnections(new Set());
      return;
    }
    
    setFocusedTable(tableName);
    
    // Find only immediate connections (1 level up and 1 level down)
    const connections = lineageData.connections;
    const immediateConnections = new Set();
    
    // Add the focused table itself
    immediateConnections.add(tableName);
    
    // Add tables that feed into this table (immediate previous level)
    connections
      .filter(conn => conn.targetTable === tableName)
      .forEach(conn => immediateConnections.add(conn.sourceTable));
    
    // Add tables that this table feeds into (immediate next level)
    connections
      .filter(conn => conn.sourceTable === tableName)
      .forEach(conn => immediateConnections.add(conn.targetTable));
    
    setFocusedTableConnections(immediateConnections);
  };

  const clearFocus = () => {
    setFocusedTable(null);
    setFocusedTableConnections(new Set());
  };

  // Force layout recalculation when focus mode changes
  useEffect(() => {
    if (lineageData && (focusedTable || focusedTableConnections.size > 0)) {
      // Clear positions to force recalculation
      tablePositionsRef.current.clear();
    }
  }, [focusedTable, focusedTableConnections, lineageData]);

  // Function to get connected tables (tables that have at least one connection)
  const getConnectedTables = (tables, connections) => {
    const connectedTableNames = new Set();
    
    // Add all tables that appear in connections
    connections.forEach(conn => {
      connectedTableNames.add(conn.sourceTable);
      connectedTableNames.add(conn.targetTable);
    });
    
    // Return tables that have connections (even if they have zero columns)
    return tables.filter(table => connectedTableNames.has(table.name));
  };


  const getTransformationColor = (type) => {
    switch(type) {
      case 'aggregate': return '#f59e0b';
      case 'arithmetic': return '#06b6d4';
      case 'case': return '#ec4899';
      case 'direct': return '#3b82f6';
      case 'function': return '#8b5cf6';
      case 'aggr_func': return '#f59e0b';
      case 'binary_expr': return '#06b6d4';
      default: return '#3b82f6';
    }
  };

  const renderTableDetails = () => {
    if (!lineageData || !lineageData.tables) return null;

    return (
      <div style={{ 
        padding: '20px',
        height: '100%',
        overflowY: 'auto',
        backgroundColor: theme === 'dark' ? '#0b0f14' : '#f7f7f5'
      }}>
        <div style={{ 
          maxWidth: '1200px', 
          margin: '0 auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px'
        }}>
          {/* Header */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '16px 20px',
            backgroundColor: theme === 'dark' ? '#1f2937' : '#ffffff',
            borderRadius: '8px',
            border: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`,
            boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)'
          }}>
            <div>
              <h2 style={{ 
                fontSize: '20px', 
                fontWeight: 'bold', 
                color: theme === 'dark' ? '#e5e7eb' : '#111827',
                margin: 0
              }}>
                All Tables & Columns
              </h2>
              <p style={{ 
                fontSize: '14px', 
                color: theme === 'dark' ? '#9ca3af' : '#6b7280',
                margin: '4px 0 0 0'
              }}>
                Complete overview of all tables and their column definitions
              </p>
            </div>
            <div style={{
              fontSize: '14px',
              padding: '8px 16px',
              backgroundColor: theme === 'dark' ? '#374151' : '#f3f4f6',
              borderRadius: '6px',
              color: theme === 'dark' ? '#e5e7eb' : '#111827',
              fontWeight: 600
            }}>
              {lineageData.tables.length} tables
            </div>
          </div>

          {/* Tables Grid */}
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', 
            gap: '16px' 
          }}>
            {lineageData.tables.filter(table => table.columns && table.columns.length > 0).map((table, tableIndex) => (
              <div key={table.name} style={{ 
                backgroundColor: theme === 'dark' ? '#1f2937' : '#ffffff',
                borderRadius: '8px',
                border: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`,
                boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)',
                overflow: 'hidden'
              }}>
                {/* Table Header */}
                <div style={{
                  padding: '16px',
                  backgroundColor: theme === 'dark' ? '#374151' : '#f9fafb',
                  borderBottom: `1px solid ${theme === 'dark' ? '#4b5563' : '#e5e7eb'}`,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px'
                }}
                onClick={() => toggleTable(table.name)}
                >
                  <div style={{ 
                    width: '12px', 
                    height: '12px', 
                    borderRadius: '50%', 
                    backgroundColor: table.type === 'target' 
                      ? '#2563eb' 
                      : table.type === 'source' 
                      ? '#4b5563' 
                      : '#10b981',
                    flexShrink: 0
                  }}></div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ 
                      fontSize: '12px', 
                      color: theme === 'dark' ? '#9ca3af' : '#6b7280',
                      fontWeight: 500,
                      textTransform: 'uppercase',
                      letterSpacing: '0.5px'
                    }}>
                      {table.schema}
                    </div>
                    <div style={{ 
                      fontSize: '16px', 
                      fontWeight: 700,
                      color: theme === 'dark' ? '#e5e7eb' : '#111827',
                      marginTop: '2px'
                    }}>
                      {table.tableName}
                    </div>
                  </div>
                  <div style={{
                    fontSize: '11px',
                    padding: '4px 8px',
                    borderRadius: '4px',
                    backgroundColor: table.type === 'target' 
                      ? '#2563eb' 
                      : table.type === 'source' 
                      ? '#4b5563' 
                      : '#10b981',
                    color: 'white',
                    fontWeight: 600,
                    textTransform: 'uppercase'
                  }}>
                    {table.type === 'target' ? 'Target' : table.type === 'source' ? 'Source' : 'View'}
                  </div>
                  <div style={{ fontSize: '14px', color: theme === 'dark' ? '#6b7280' : '#9ca3af' }}>
                    {expandedTables.has(table.name) ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </div>
                </div>

                {/* Table Columns */}
                {expandedTables.has(table.name) && (
                  <div style={{ padding: '16px' }}>
                    {table.columns.length === 0 ? (
                      <div style={{ 
                        textAlign: 'center', 
                        color: theme === 'dark' ? '#6b7280' : '#9ca3af', 
                        fontSize: '14px', 
                        padding: '20px',
                        fontStyle: 'italic'
                      }}>
                        No columns detected
                      </div>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {table.columns.map((column, columnIndex) => {
                          const hasConnection = lineageData.connections.some(c => 
                            (c.sourceTable === table.name && c.sourceColumn === column.name) ||
                            (c.targetTable === table.name && c.targetColumn === column.name)
                          );
                          
                          return (
                            <div
                              key={columnIndex}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '12px',
                                padding: '10px 12px',
                                borderRadius: '6px',
                                backgroundColor: hasConnection 
                                  ? (theme === 'dark' ? 'rgba(59, 130, 246, 0.15)' : 'rgba(59, 130, 246, 0.08)')
                                  : (theme === 'dark' ? 'rgba(55, 65, 81, 0.3)' : 'rgba(243, 244, 246, 0.8)'),
                                fontSize: '14px',
                                borderLeft: hasConnection ? '4px solid #3b82f6' : '4px solid transparent',
                                transition: 'all 0.2s ease',
                                overflow: 'hidden',
                                minWidth: 0
                              }}
                            >
                              <div style={{ 
                                width: '8px', 
                                height: '8px', 
                                borderRadius: '50%', 
                                backgroundColor: hasConnection ? '#3b82f6' : '#6b7280',
                                flexShrink: 0
                              }}></div>
                              <span style={{ 
                                fontFamily: 'monospace', 
                                color: theme === 'dark' ? '#e5e7eb' : '#111827',
                                flex: 1,
                                fontWeight: 500,
                                wordBreak: 'break-word',
                                overflowWrap: 'break-word',
                                maxWidth: '100%'
                              }}>
                                {toDisplay(column.name)}
                              </span>
                              {column.expression && column.expression !== 'column' && (
                                <span style={{ 
                                  fontSize: '10px', 
                                  backgroundColor: theme === 'dark' ? getTransformationColor(column.expression) : 'transparent',
                                  color: theme === 'dark' ? 'white' : getTransformationColor(column.expression),
                                  padding: '2px 6px',
                                  borderRadius: '3px',
                                  border: theme === 'dark' ? 'none' : `1px solid ${getTransformationColor(column.expression)}`,
                                  fontWeight: 600
                                }}>
                                  {toDisplay(column.expression)}
                                </span>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  };

  const renderLineage = () => {
    if (!lineageData || !lineageData.tables || !lineageData.connections) return null;
    

    // Standardized height constants - must match layoutTablesWithDagre function
    const columnHeight = 28;
    const tableHeaderHeight = 60; // Increased to accommodate table name and schema
    const tablePadding = 12; // Changed from 16 to match layoutTablesWithDagre
    const columnSpacing = 4; // Added for column marginBottom
    const tableBottomMargin = 15; // Additional margin at bottom of table

    const findColumnIndex = (table, columnName) => {
      if (!table || !table.columns || !columnName) return -1;
      // 1) exact match
      let idx = table.columns.findIndex(c => c.name === columnName);
      if (idx !== -1) return idx;
      // 2) case-insensitive
      const lower = String(columnName).toLowerCase();
      idx = table.columns.findIndex(c => String(c.name).toLowerCase() === lower);
      if (idx !== -1) return idx;
      // 3) trim quoting characters if any
      const trimQuotes = (s) => {
        let out = String(s);
        if (out.startsWith('`') || out.startsWith('"') || out.startsWith('[')) out = out.slice(1);
        if (out.endsWith('`') || out.endsWith('"') || out.endsWith(']')) out = out.slice(0, -1);
        return out;
      };
      const trimmed = trimQuotes(columnName);
      if (trimmed !== columnName) {
        return table.columns.findIndex(c => trimQuotes(c.name) === trimmed);
      }
      return -1;
    };

    // Filter connections to exclude hidden tables and respect focus mode
    let visibleConnections;
    if (focusedTable && focusedTableConnections.size > 0) {
      // In focus mode, only show connections involving the focused table and its immediate connections
      visibleConnections = lineageData.connections.filter(conn => 
        focusedTableConnections.has(conn.sourceTable) && 
        focusedTableConnections.has(conn.targetTable) &&
        !hiddenPreviousLevels?.has(conn.sourceTable) && 
        !hiddenPreviousLevels?.has(conn.targetTable) &&
        !hiddenNextLevels?.has(conn.sourceTable) && 
        !hiddenNextLevels?.has(conn.targetTable)
      );
    } else {
      // Normal mode - show all connections except those involving hidden tables
      visibleConnections = lineageData.connections.filter(conn => 
        !hiddenPreviousLevels?.has(conn.sourceTable) && 
        !hiddenPreviousLevels?.has(conn.targetTable) &&
        !hiddenNextLevels?.has(conn.sourceTable) && 
        !hiddenNextLevels?.has(conn.targetTable)
      );
    }

    // Determine which column-level connections to render: only those in hovered set
    const columnConnectionsToRender = showAllColumnConnections
      ? visibleConnections
      : (hoveredConnections.length > 0 
        ? visibleConnections.filter(c => hoveredConnections.some(h => h.sourceTable === c.sourceTable && h.sourceColumn === c.sourceColumn && h.targetTable === c.targetTable && h.targetColumn === c.targetColumn))
        : []);

    // Use dagre for layout
    const allPositions = layoutTablesWithDagre(lineageData.tables, visibleConnections);

    // Compute dynamic canvas size to accommodate all tables with extra margin
    const extraMargin = 200;
    const minX = Math.min(0, ...allPositions.map(t => t.x));
    const minY = Math.min(0, ...allPositions.map(t => t.y));
    const maxX = Math.max(0, ...allPositions.map(t => t.x + t.width));
    const maxY = Math.max(0, ...allPositions.map(t => t.y + t.height));
    const canvasWidth = Math.ceil((maxX - minX) + extraMargin);
    const canvasHeight = Math.ceil((maxY - minY) + extraMargin);

    return (
      <div 
        className="canvas-bg"
        style={{
          transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
          transformOrigin: '0 0',
          transition: isDragging ? 'none' : 'transform 0.3s ease-out',
          position: 'absolute',
          top: 0,
          left: 0,
          width: `${canvasWidth}px`,
          height: `${canvasHeight}px`,
          minWidth: '100%',
          minHeight: '100%'
        }}
      >
        <svg style={{ 
          position: 'absolute', 
          top: 0, 
          left: 0, 
          width: '100%', 
          height: '100%', 
          overflow: 'visible',
          pointerEvents: 'none'
        }}>
          <defs>
            <marker
              id="arrowhead"
              markerWidth="10"
              markerHeight="10"
              refX="9"
              refY="3"
              orient="auto"
            >
              <polygon points="0 0, 10 3, 0 6" fill="#3b82f6" />
            </marker>
            <linearGradient id="lineGradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.8" />
              <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0.8" />
            </linearGradient>
            <linearGradient id="lineGradientHover" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#2563eb" stopOpacity="1" />
              <stop offset="100%" stopColor="#7c3aed" stopOpacity="1" />
            </linearGradient>
            <filter id="glow">
              <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
              <feMerge>
                <feMergeNode in="coloredBlur"/>
                <feMergeNode in="SourceGraphic"/>
              </feMerge>
            </filter>
          </defs>
          
          {visibleConnections.map((conn, idx) => {
            const sourceTable = allPositions.find(t => t.name === conn.sourceTable);
            const targetTable = allPositions.find(t => t.name === conn.targetTable);
            
            if (!sourceTable || !targetTable || !sourceTable.x || !targetTable.x) return null;
            
            const sourceExpanded = expandedTables.has(sourceTable.name);
            const targetExpanded = expandedTables.has(targetTable.name);

            
            
            const lineColor = getTransformationColor(conn.transformationType);
            const tableStroke = theme === 'dark' ? '#ffffff' : '#000000';
            
            // Render both column-level and table-level connections
            const connections = [];
            
            // 1. Column-level connection (only render if in hovered set)
            if (sourceExpanded && targetExpanded) {
              const isInColumnSet = columnConnectionsToRender.some(h => h.sourceTable === conn.sourceTable && h.sourceColumn === conn.sourceColumn && h.targetTable === conn.targetTable && h.targetColumn === conn.targetColumn);
              if (isInColumnSet) {
                const sourceColIdx = findColumnIndex(sourceTable, conn.sourceColumn);
                const targetColIdx = findColumnIndex(targetTable, conn.targetColumn);
                if (sourceColIdx !== -1 && targetColIdx !== -1) {
                  const sourceX = sourceTable.x + sourceTable.width;
                  const sourceY = sourceTable.y + tableHeaderHeight + tablePadding + (sourceColIdx * (columnHeight + columnSpacing)) + (columnHeight / 2);
                  const targetX = targetTable.x;
                  const targetY = targetTable.y + tableHeaderHeight + tablePadding + (targetColIdx * (columnHeight + columnSpacing)) + (columnHeight / 2);
                  const controlPoint1X = sourceX + (targetX - sourceX) * 0.5;
                  const controlPoint2X = targetX - (targetX - sourceX) * 0.5;
                  connections.push(
                    <g key={`column-${conn.sourceTable}-${conn.sourceColumn}-${conn.targetTable}-${conn.targetColumn}-${idx}`}>
                      <path
                        d={`M ${sourceX} ${sourceY} C ${controlPoint1X} ${sourceY}, ${controlPoint2X} ${targetY}, ${targetX} ${targetY}`}
                        fill="none"
                        stroke={lineColor}
                        strokeWidth={"2.5"}
                        opacity={"1"}
                        filter={showAllColumnConnections ? "" : "url(#glow)"}
                        markerEnd={"url(#arrowhead)"}
                        style={{ transition: 'all 0.35s' }}
                      />
                    </g>
                  );
                }
              }
            }
            
            // 2. Table-level connection (always show this as a background connection)
            const tableSourceX = sourceTable.x + sourceTable.width + 8; // Right connection point
            const tableSourceY = sourceTable.y + tableHeaderHeight / 2;
            const tableTargetX = targetTable.x - 8; // Left connection point
            const tableTargetY = targetTable.y + tableHeaderHeight / 2;
            
            const tableControlPoint1X = tableSourceX + (tableTargetX - tableSourceX) * 0.5;
            const tableControlPoint2X = tableTargetX - (tableTargetX - tableSourceX) * 0.5;
            
            connections.push(
              <g key={`table-${conn.sourceTable}-${conn.targetTable}-${idx}`}>
                <path
                  d={`M ${tableSourceX} ${tableSourceY} C ${tableControlPoint1X} ${tableSourceY}, ${tableControlPoint2X} ${tableTargetY}, ${tableTargetX} ${tableTargetY}`}
                  fill="none"
                  stroke={tableStroke}
                  strokeWidth={"2"}
                  opacity={"0.8"}
                  filter={""}
                  markerEnd={"url(#arrowhead)"}
                  style={{ transition: 'all 0.35s' }}
                />
              </g>
            );
            
            return connections;
          }).flat()}
        </svg>

        {allPositions.map((table) => {
          const isExpanded = expandedTables.has(table.name);
          const isSelected = false;
          const isSource = table.type === 'source';
          const isTarget = table.type === 'target';
          
          return (
            <div
              key={table.name}
              className="table-card"
              style={{ 
                position: 'absolute',
                left: table.x, 
                top: table.y, 
                width: table.width,
                height: table.height,
                backgroundColor: theme === 'dark' ? '#1f2937' : '#ffffff',
                borderRadius: '8px',
                boxShadow: isSelected ? '0 0 20px rgba(59, 130, 246, 0.5)' : '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
                border: isSelected ? '2px solid #3b82f6' : '2px solid #e5e7eb',
                transition: 'all 0.35s',
                overflow: 'visible',
                boxSizing: 'border-box'
              }}
            >
              {/* Table Header */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: isExpanded ? '14px 16px' : '12px 16px',
                  borderTopLeftRadius: '8px',
                  borderTopRightRadius: '8px',
                  borderBottomLeftRadius: isExpanded ? '0px' : '8px',
                  borderBottomRightRadius: isExpanded ? '0px' : '8px',
                  cursor: 'pointer',
                  background: isTarget
                    ? 'linear-gradient(135deg, #1d4ed8, #2563eb)' 
                    : isSource 
                    ? 'linear-gradient(135deg, #374151, #4b5563)'
                    : 'linear-gradient(135deg, #059669, #10b981)',
                  boxShadow: isExpanded 
                    ? 'inset 0 1px 0 rgba(255, 255, 255, 0.1)' 
                    : 'inset 0 1px 0 rgba(255, 255, 255, 0.1), 0 2px 8px rgba(0, 0, 0, 0.15)',
                  borderBottom: isExpanded ? '1px solid rgba(255, 255, 255, 0.1)' : 'none',
                  position: 'relative',
                  overflow: 'visible',
                  transition: 'all 0.35s ease'
                }}
                onClick={() => {
                  toggleTable(table.name);
                }}
              >
                {/* Left Connection Point - Previous Level Expand */}
                {(() => {
                  const hasPreviousLevel = lineageData?.connections?.some(conn => conn.targetTable === table.name);
                  const previousTables = lineageData?.connections
                    ?.filter(conn => conn.targetTable === table.name)
                    ?.map(conn => conn.sourceTable) || [];
                  
                  if (!hasPreviousLevel || previousTables.length === 0) return null;
                  
                  // In focus mode: show expand button if there are additional levels beyond immediate connections
                  if (focusedTable && focusedTableConnections.size > 0) {
                    // Check if there are previous tables not in the current focused connections
                    const hasAdditionalLevels = previousTables.some(tableName => !focusedTableConnections.has(tableName));
                    if (!hasAdditionalLevels) return null;
                  } else {
                    // Normal mode: check if ANY previous tables are hidden
                    const anyPreviousHidden = previousTables.some(tableName => hiddenPreviousLevels?.has(tableName));
                    if (!anyPreviousHidden) return null;
                  }
                  
                  return (
                    <div
                      style={{
                        position: 'absolute',
                        left: '-8px',
                        top: '50%',
                        transform: 'translateY(-50%)',
                        width: '16px',
                        height: '16px',
                        borderRadius: '50%',
                        backgroundColor: '#10b981',
                        border: '2px solid white',
                        boxShadow: '0 2px 4px rgba(0, 0, 0, 0.3)',
                        zIndex: 10,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '12px',
                        fontWeight: 'bold',
                        color: 'white'
                      }}
                      onClick={(e) => {
                        e.stopPropagation();
                        expandTableLevel(table.name, 'left');
                      }}
                    >
                      +
                    </div>
                  );
                })()}

                {/* Right Connection Point - Next Level Expand */}
                {(() => {
                  const hasNextLevel = lineageData?.connections?.some(conn => conn.sourceTable === table.name);
                  const nextTables = lineageData?.connections
                    ?.filter(conn => conn.sourceTable === table.name)
                    ?.map(conn => conn.targetTable) || [];
                  
                  if (!hasNextLevel || nextTables.length === 0) return null;
                  
                  // In focus mode: show expand button if there are additional levels beyond immediate connections
                  if (focusedTable && focusedTableConnections.size > 0) {
                    // Check if there are next tables not in the current focused connections
                    const hasAdditionalLevels = nextTables.some(tableName => !focusedTableConnections.has(tableName));
                    if (!hasAdditionalLevels) return null;
                  } else {
                    // Normal mode: check if ANY next tables are hidden
                    const anyNextHidden = nextTables.some(tableName => hiddenNextLevels?.has(tableName));
                    if (!anyNextHidden) return null;
                  }
                  
                  return (
                    <div
                      style={{
                        position: 'absolute',
                        right: '-8px',
                        top: '50%',
                        transform: 'translateY(-50%)',
                        width: '16px',
                        height: '16px',
                        borderRadius: '50%',
                        backgroundColor: '#10b981',
                        border: '2px solid white',
                        boxShadow: '0 2px 4px rgba(0, 0, 0, 0.3)',
                        zIndex: 10,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '12px',
                        fontWeight: 'bold',
                        color: 'white'
                      }}
                      onClick={(e) => {
                        e.stopPropagation();
                        expandTableLevel(table.name, 'right');
                      }}
                    >
                      +
                    </div>
                  );
                })()}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, minWidth: 0 }}>
                  <button style={{ 
                    background: 'transparent', 
                    border: 'none', 
                    color: 'white',
                    cursor: 'pointer',
                    padding: '4px',
                    borderRadius: '4px',
                    display: 'flex',
                    alignItems: 'center'
                  }}>
                    {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </button>
                  <Database size={16} style={{ flexShrink: 0, color: 'white' }} />
                  <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, flex: 1, gap: isExpanded ? '2px' : '1px' }}>
                    <span style={{ 
                      fontSize: isExpanded ? '11px' : '10px', 
                      color: 'rgba(255, 255, 255, 0.8)', 
                      fontWeight: 500,
                      textTransform: 'uppercase',
                      letterSpacing: '0.5px',
                      lineHeight: '1.2'
                    }}>{toDisplay(table.schema)}</span>
                    <span style={{ 
                      fontSize: isExpanded ? '15px' : '14px', 
                      fontWeight: isExpanded ? 700 : 600, 
                      color: 'white', 
                      overflow: 'hidden', 
                      textOverflow: 'ellipsis', 
                      whiteSpace: 'nowrap',
                      lineHeight: '1.3',
                      textShadow: isExpanded ? '0 1px 2px rgba(0, 0, 0, 0.3)' : '0 1px 1px rgba(0, 0, 0, 0.2)'
                    }}>{toDisplay(table.tableName)}</span>
                  </div>
                </div>
                <div style={{
                  fontSize: isExpanded ? '11px' : '10px',
                  padding: isExpanded ? '6px 10px' : '4px 8px',
                  borderRadius: '6px',
                  backgroundColor: isExpanded ? 'rgba(255, 255, 255, 0.2)' : 'rgba(255, 255, 255, 0.15)',
                  color: 'white',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                  backdropFilter: 'blur(10px)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  boxShadow: isExpanded ? '0 2px 4px rgba(0, 0, 0, 0.2)' : '0 1px 2px rgba(0, 0, 0, 0.1)',
                  transition: 'all 0.2s ease'
                }}>
                  {isTarget ? 'Target' : isSource ? 'Source' : 'Table'}
                </div>
              </div>

              {/* Columns */}
              {isExpanded && (
                <div style={{ padding: `${tablePadding}px`, paddingBottom: `${tablePadding + tableBottomMargin}px`, overflow: 'hidden', boxSizing: 'border-box', position: 'relative' }}>
                  {table.columns.length === 0 ? (
                    <div style={{ textAlign: 'center', color: '#9ca3af', fontSize: '12px', padding: '8px' }}>
                      No columns detected
                    </div>
                  ) : (
                    table.columns.map((col, idx) => {
                      const hasConnection = lineageData.connections.some(c => 
                        (c.sourceTable === table.name && c.sourceColumn === col.name) ||
                        (c.targetTable === table.name && c.targetColumn === col.name)
                      );
                      
                      const isHoveredCol = hoveredConnections.some(h => 
                        (h.sourceTable === table.name && h.sourceColumn === col.name) ||
                        (h.targetTable === table.name && h.targetColumn === col.name)
                      );
                      
                      const dimOthers = !showAllColumnConnections && hoveredConnections.length > 0;
                      const isActive = showAllColumnConnections ? hasConnection : (hoveredConnections.length > 0 && isHoveredCol);
                      
                      return (
                        <div
                          key={idx}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            padding: '6px 12px',
                            borderRadius: '4px',
                            fontSize: '14px',
                            marginBottom: `${columnSpacing}px`,
                            backgroundColor: isActive
                              ? (theme === 'dark' ? 'rgba(59, 130, 246, 0.35)' : 'rgba(59, 130, 246, 0.18)')
                              : (theme === 'dark' ? 'rgba(55, 65, 81, 0.5)' : '#f3f4f6'),
                            transition: 'all 0.35s',
                            cursor: 'pointer',
                            borderLeft: col.isJoinKey ? '3px solid #f59e0b' : 'none',
                            opacity: dimOthers ? (isActive ? 1 : 0.25) : 1,
                            overflow: 'hidden',
                            minWidth: 0,
                            maxWidth: '100%',
                            boxSizing: 'border-box'
                          }}
                          onMouseEnter={() => {
                            if (showAllColumnConnections) return; // keep full set
                            const conns = lineageData.connections.filter(c => 
                              (c.sourceTable === table.name && c.sourceColumn === col.name) ||
                              (c.targetTable === table.name && c.targetColumn === col.name)
                            );
                            setHoveredConnections(conns);
                            // Auto-expand involved tables if not expanded
                            const involvedTables = Array.from(new Set(conns.flatMap(c => [c.sourceTable, c.targetTable])));
                            const toExpand = involvedTables.filter(tn => !expandedTables.has(tn));
                            if (toExpand.length > 0) {
                              ensureTablesExpanded(toExpand);
                            }
                          }}
                          onMouseLeave={() => {
                            if (showAllColumnConnections) return; // preserve showing all
                            setHoveredConnections([]);
                            // Do not collapse auto-expanded tables on hover end per user request
                          }}
                        >
                          <div style={{ 
                            width: '8px', 
                            height: '8px', 
                            borderRadius: '50%', 
                            backgroundColor: hasConnection ? '#60a5fa' : '#6b7280',
                            flexShrink: 0
                          }}></div>
                          <span style={{ 
                            fontFamily: 'monospace', 
                            color: theme === 'dark' ? '#e5e7eb' : '#111827', 
                            flex: 1, 
                            overflow: 'hidden', 
                            textOverflow: 'ellipsis', 
                            whiteSpace: 'nowrap' 
                          }}>
                            {toDisplay(col.name)}
                          </span>
                          {col.expression && col.expression !== 'column' && (
                            <span style={{ 
                              fontSize: '10px', 
                              backgroundColor: theme === 'dark' ? getTransformationColor(col.expression) : 'transparent',
                              color: theme === 'dark' ? 'white' : getTransformationColor(col.expression),
                              padding: '2px 6px',
                              borderRadius: '3px',
                              border: theme === 'dark' ? 'none' : `1px solid ${getTransformationColor(col.expression)}`
                            }}>
                              {toDisplay(col.expression)}
                            </span>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  const layoutProceduresWithDagre = (nodes, connections) => {
    if (!nodes || !connections) return [];
    
    const nodeHeaderHeight = 60;
    const nodePadding = 12;
    const itemHeight = 28; // match visual row height (padding + font)
    const rowSpacing = 6;  // margin between rows in render
    const nodeBottomMargin = 15;
    const defaultNodeWidth = 320;
    const columnNodeWidth = 220;

    const calculateNodeHeight = (node) => {
      if (node.type === 'column') return 48;
      if (node.type === 'table' && Array.isArray(node.columns)) {
        const isExpanded = expandedProcedures.has(node.name);
        if (!isExpanded) return nodeHeaderHeight;
        const hasCols = node.columns.length > 0;
        const columnsTitleHeight = hasCols ? 20 : 0; // "Columns" label
        const columnsHeight = hasCols 
          ? (node.columns.length * (itemHeight + rowSpacing)) - rowSpacing // stacked rows
          : 0;
        return nodeHeaderHeight + nodePadding + columnsTitleHeight + columnsHeight + nodePadding + nodeBottomMargin;
      }
      const isExpanded = expandedProcedures.has(node.name);
      if (!isExpanded) return nodeHeaderHeight;
      
      let itemsHeight = 0;
      if (isExpanded) {
        itemsHeight += node.parameters?.length * itemHeight || 0;
        itemsHeight += (node.reads_tables?.length || 0) * itemHeight;
        itemsHeight += (node.writes_tables?.length || 0) * itemHeight;
        itemsHeight += (node.calls_procedures?.length || 0) * itemHeight;
        itemsHeight += (node.called_by?.length || 0) * itemHeight;
        if (itemsHeight > 0) itemsHeight += nodePadding;
      }
      
      return nodeHeaderHeight + nodePadding + itemsHeight + nodePadding + nodeBottomMargin;
    };

    // Separate base nodes (laid out by dagre) and column nodes (positioned relative to parent table)
    const baseNodes = nodes.filter(n => n.type !== 'column');
    const columnNodes = nodes.filter(n => n.type === 'column');

    const g = new dagre.graphlib.Graph();
    g.setGraph({ 
      rankdir: 'LR', 
      ranksep: 300, 
      nodesep: 100,
      edgesep: 50,
      marginx: 50,
      marginy: 50
    });
    g.setDefaultEdgeLabel(() => ({}));

    baseNodes.forEach(node => {
      const height = calculateNodeHeight(node);
      g.setNode(node.name, { 
        label: node.name, 
        width: node.type === 'column' ? columnNodeWidth : defaultNodeWidth, 
        height: height 
      });
    });

    const addedEdges = new Set();
    // Only add edges between base nodes to avoid forcing column nodes into layout
    connections.forEach(conn => {
      const isBaseEdge = baseNodes.find(n => n.name === conn.source) && baseNodes.find(n => n.name === conn.target);
      if (!isBaseEdge) return;
      const edgeKey = `${conn.source}->${conn.target}`;
      if (!addedEdges.has(edgeKey)) {
        g.setEdge(conn.source, conn.target, {});
        addedEdges.add(edgeKey);
      }
    });

    dagre.layout(g);

    // Map positions for base nodes
    const positioned = baseNodes.map(node => {
      const layoutNode = g.node(node.name);
      return {
        ...node,
        x: layoutNode.x - defaultNodeWidth / 2,
        y: layoutNode.y - layoutNode.height / 2,
        width: defaultNodeWidth,
        height: layoutNode.height
      };
    });

    // Position column nodes to the right of their parent table, stacked
    const tableToColumns = new Map();
    columnNodes.forEach(col => {
      const parent = col.parentTable;
      if (!parent) return;
      if (!tableToColumns.has(parent)) tableToColumns.set(parent, []);
      tableToColumns.get(parent).push(col);
    });

    tableToColumns.forEach((cols, parentName) => {
      const tableNode = positioned.find(n => n.name === parentName);
      if (!tableNode) return; // parent not visible; skip
      cols.forEach((col, idx) => {
        const colX = tableNode.x + tableNode.width + 40; // right side spacing
        const startY = tableNode.y; // align from top of table node
        const colY = startY + nodeHeaderHeight + 10 + idx * (48 + 8); // after header, stacked
        positioned.push({
          ...col,
          x: colX,
          y: colY,
          width: columnNodeWidth,
          height: 48
        });
      });
    });

    return positioned;
  };

  const getConnectionColor = (connType) => {
    switch(connType) {
      case 'procedure_call':
      case 'function_call':
        return '#3b82f6';
      case 'table_read':
        return '#10b981';
      case 'table_write':
        return '#f59e0b';
      case 'table_create':
        return '#f59e0b';
      case 'column_read':
        return '#22c55e';
      case 'column_write':
        return '#f59e0b';
      case 'column_update':
        return '#fbbf24';
      case 'column_of':
        return '#9ca3af';
      default:
        return '#6b7280';
    }
  };

  const toggleProcedure = (procName) => {
    setExpandedProcedures(prev => {
      const next = new Set(prev);
      if (next.has(procName)) {
        next.delete(procName);
      } else {
        next.add(procName);
      }
      return next;
    });
  };

  const renderProcedureLineage = () => {
    if (!procedureLineageData || !procedureLineageData.nodes || !procedureLineageData.connections) {
      return (
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center', 
          height: '100%',
          color: theme === 'dark' ? '#9ca3af' : '#6b7280'
        }}>
          <div style={{ textAlign: 'center' }}>
            <Database size={64} style={{ margin: '0 auto', color: '#4b5563', marginBottom: '16px' }} />
            <p style={{ fontSize: '18px', fontWeight: 500 }}>No procedure lineage data</p>
            <p style={{ fontSize: '14px', marginTop: '8px' }}>Select a procedure from the sidebar to view its lineage</p>
          </div>
        </div>
      );
    }

    // Require a selection to display; otherwise show instruction
    if (!selectedProcedure) {
      return (
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center', 
          height: '100%',
          color: theme === 'dark' ? '#9ca3af' : '#6b7280'
        }}>
          <div style={{ textAlign: 'center' }}>
            <p style={{ fontSize: '16px', fontWeight: 500 }}>Select a procedure or function from the left panel.</p>
          </div>
        </div>
      );
    }

    // Show only selected procedure and its immediate connections
    let visibleNodes = [];
    let visibleConnections = [];
    const relatedNodes = new Set([selectedProcedure]);
    procedureLineageData.connections.forEach(conn => {
      if (conn.source === selectedProcedure || conn.target === selectedProcedure) {
        relatedNodes.add(conn.source);
        relatedNodes.add(conn.target);
      }
    });
    // Start with non-column nodes only
    const baseNodes = procedureLineageData.nodes.filter(n => relatedNodes.has(n.name) && n.type !== 'column');
    visibleConnections = procedureLineageData.connections.filter(conn => 
      relatedNodes.has(conn.source) && relatedNodes.has(conn.target) &&
      conn.type !== 'column_of' && conn.type !== 'column_read' && conn.type !== 'column_write' && conn.type !== 'column_update'
    );

    // Build table columns from raw report and statement lineage if available
    const selectedIsFunction = !!procedureLineage?.functions?.[selectedProcedure];
    const selectedIsTrigger = !!procedureLineage?.triggers?.[selectedProcedure];
    const selectedRaw = selectedIsTrigger
      ? procedureLineage?.triggers?.[selectedProcedure]
      : (selectedIsFunction 
        ? procedureLineage?.functions?.[selectedProcedure]
        : procedureLineage?.procedures?.[selectedProcedure]);

    const normalizeFqCol = (entry) => {
      if (!entry) return '';
      if (typeof entry === 'string') return entry;
      if (entry.qualified_name) return entry.qualified_name;
      // Check for table_list first (new format), then fall back to table (backward compatibility)
      const tableName = entry.table_list || entry.table;
      if (tableName && entry.column) return `${tableName}.${entry.column}`;
      if (entry.schema && entry.name) return `${entry.schema}.${entry.name}`;
      if (Array.isArray(entry)) return entry.join('.');
      return String(entry);
    };

    const readCols = new Set((selectedRaw?.columns_read || []).map(normalizeFqCol).filter(Boolean));
    const writeCols = new Set((selectedRaw?.columns_written || []).map(normalizeFqCol).filter(Boolean));
    const updateCols = new Set((selectedRaw?.columns_updated || []).map(normalizeFqCol).filter(Boolean));

    // Collect involved tables: from edges and from columns_read/write lists
    const involvedTables = new Set();
    visibleConnections.forEach(c => {
      if (c.type === 'table_read' && c.target === selectedProcedure) involvedTables.add(c.source);
      if (c.type === 'table_write' && c.source === selectedProcedure) involvedTables.add(c.target);
    });
    const addTableFromFqcol = (fqcol) => {
      const parts = String(fqcol).split('.');
      // Only add a table from column when it has schema.table.column; table-only entries are already handled
      if (parts.length >= 3) involvedTables.add(parts.slice(0, -1).join('.'));
    };
    readCols.forEach(addTableFromFqcol);
    writeCols.forEach(addTableFromFqcol);
    updateCols.forEach(addTableFromFqcol);

    // Also include created temp tables explicitly
    (selectedRaw?.creates_temp_tables || []).forEach(t => involvedTables.add(t));

    // Map existing base nodes by name for merging
    const nameToNode = new Map(baseNodes.map(n => [n.name, { ...n }]));

    // Helper: get full columns from statement lineage if available
    const getStatementTableColumns = (tableName) => {
      if (!lineageData?.tables) return null;
      const t = lineageData.tables.find(t => t.name === tableName);
      if (!t) return null;
      return t.columns?.map(c => c.name) || [];
    };

    // Create enriched table nodes with columns grouped by table
    involvedTables.forEach(tableName => {
      const existing = nameToNode.get(tableName) || { name: tableName, schema: tableName.split('.')?.[0], nodeName: tableName.split('.')?.slice(1).join('.') || tableName, type: 'table' };
      // Derive columns from statement lineage or from referenced columns
      const fullCols = getStatementTableColumns(tableName);
      const referencedCols = new Set();
      readCols.forEach(fq => { const p = fq.split('.'); if (p.length >= 3 && fq.startsWith(tableName + '.')) referencedCols.add(p.pop()); });
      writeCols.forEach(fq => { const p = fq.split('.'); if (p.length >= 3 && fq.startsWith(tableName + '.')) referencedCols.add(p.pop()); });
      updateCols.forEach(fq => { const p = fq.split('.'); if (p.length >= 3 && fq.startsWith(tableName + '.')) referencedCols.add(p.pop()); });
      const finalCols = fullCols && fullCols.length > 0 ? fullCols : Array.from(referencedCols);
      existing.columns = finalCols.map(col => ({
        name: col,
        isRead: readCols.has(`${tableName}.${col}`),
        isWrite: writeCols.has(`${tableName}.${col}`),
        isUpdate: updateCols.has(`${tableName}.${col}`)
      }));
      nameToNode.set(tableName, existing);
    });

    // Only keep selected node and involved tables (drop any extra)
    const selectedNode = procedureLineageData.nodes.find(n => n.name === selectedProcedure);
    visibleNodes = [
      ...(selectedNode ? [{ ...selectedNode }] : []),
      ...Array.from(involvedTables).map(tn => nameToNode.get(tn)).filter(Boolean)
    ];

    const allPositions = layoutProceduresWithDagre(visibleNodes, visibleConnections);

    const extraMargin = 200;
    const minX = Math.min(0, ...allPositions.map(n => n.x));
    const minY = Math.min(0, ...allPositions.map(n => n.y));
    const maxX = Math.max(0, ...allPositions.map(n => n.x + n.width));
    const maxY = Math.max(0, ...allPositions.map(n => n.y + n.height));
    const canvasWidth = Math.ceil((maxX - minX) + extraMargin);
    const canvasHeight = Math.ceil((maxY - minY) + extraMargin);

    const nodeHeaderHeight = 60;
    const nodePadding = 12;
    const itemHeight = 28; // keep in sync with layout
    const rowSpacing = 6;  // keep in sync with layout
    const columnsTitleHeight = 20;

    return (
      <div 
        className="canvas-bg"
        style={{
          transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
          transformOrigin: '0 0',
          transition: isDragging ? 'none' : 'transform 0.3s ease-out',
          position: 'absolute',
          top: 0,
          left: 0,
          width: `${canvasWidth}px`,
          height: `${canvasHeight}px`,
          minWidth: '100%',
          minHeight: '100%'
        }}
      >
        <svg style={{ 
          position: 'absolute', 
          top: 0, 
          left: 0, 
          width: '100%', 
          height: '100%', 
          overflow: 'visible',
          pointerEvents: 'none'
        }}>
          <defs>
            <marker
              id="arrowhead-proc"
              markerWidth="10"
              markerHeight="10"
              refX="10"
              refY="5"
              markerUnits="userSpaceOnUse"
              orient="auto"
            >
              <polygon points="0 0, 10 5, 0 10" fill="#3b82f6" />
            </marker>
          </defs>
          
          {visibleConnections.map((conn, idx) => {
            const sourceNode = allPositions.find(n => n.name === conn.source);
            const targetNode = allPositions.find(n => n.name === conn.target);
            
            if (!sourceNode || !targetNode || !sourceNode.x || !targetNode.x) return null;
            
            const sourceX = sourceNode.x + sourceNode.width;
            const sourceY = sourceNode.y + nodeHeaderHeight / 2;
            const targetX = targetNode.x;
            const targetY = targetNode.y + nodeHeaderHeight / 2;
            
            const controlPoint1X = sourceX + (targetX - sourceX) * 0.5;
            const controlPoint2X = targetX - (targetX - sourceX) * 0.5;
            
            const lineColor = getConnectionColor(conn.type);
            const dim = hoveredProcConnections.length > 0;
            
            return (
              <path
                key={`proc-conn-${idx}`}
                d={`M ${sourceX} ${sourceY} C ${controlPoint1X} ${sourceY}, ${controlPoint2X} ${targetY}, ${targetX} ${targetY}`}
                fill="none"
                stroke={lineColor}
                strokeWidth={dim ? 1.5 : 2}
                opacity={dim ? 0.25 : 0.8}
                markerEnd="url(#arrowhead-proc)"
              />
            );
          })}

          {(() => {
            // Render hover column-level flows
            if (!selectedProcedure || hoveredProcConnections.length === 0) return null;
            const procNode = allPositions.find(n => n.name === selectedProcedure);
            if (!procNode) return null;
            const paths = [];
            hoveredProcConnections.forEach((h, i) => {
              const tableNode = allPositions.find(n => n.name === h.tableName);
              if (!tableNode || !Array.isArray(tableNode.columns)) return;
              const idx = tableNode.columns.findIndex(c => c.name === h.columnName);
              if (idx === -1) return;
              // Column row center accounting for padding, title and spacing
              const colYCenter = tableNode.y 
                + nodeHeaderHeight 
                + nodePadding 
                + columnsTitleHeight 
                + idx * (itemHeight + rowSpacing)
                + itemHeight / 2;
              const lineColor = h.kind === 'read' ? getConnectionColor('column_read') : (h.kind === 'update' ? getConnectionColor('column_update') : getConnectionColor('column_write'));
              if (h.kind === 'read') {
                const sourceX = tableNode.x + tableNode.width + 4;
                const sourceY = colYCenter;
                const targetX = procNode.x - 4;
                const targetY = procNode.y + nodeHeaderHeight / 2;
                const c1 = sourceX + (targetX - sourceX) * 0.5;
                const c2 = targetX - (targetX - sourceX) * 0.5;
                paths.push(
                  <path key={`hover-read-${i}`} d={`M ${sourceX} ${sourceY} C ${c1} ${sourceY}, ${c2} ${targetY}, ${targetX} ${targetY}`} fill="none" stroke={lineColor} strokeWidth="3" opacity="0.95" markerEnd="url(#arrowhead-proc)" />
                );
              } else {
                const sourceX = procNode.x + procNode.width + 4;
                const sourceY = procNode.y + nodeHeaderHeight / 2;
                const targetX = tableNode.x - 4;
                const targetY = colYCenter;
                const c1 = sourceX + (targetX - sourceX) * 0.5;
                const c2 = targetX - (targetX - sourceX) * 0.5;
                paths.push(
                  <path key={`hover-write-${i}`} d={`M ${sourceX} ${sourceY} C ${c1} ${sourceY}, ${c2} ${targetY}, ${targetX} ${targetY}`} fill="none" stroke={lineColor} strokeWidth="3" opacity="0.95" markerEnd="url(#arrowhead-proc)" />
                );
              }
            });
            return paths;
          })()}
        </svg>

        {allPositions.map((node) => {
          const isExpanded = expandedProcedures.has(node.name);
          const isSelected = selectedProcedure === node.name;
          const isFunction = node.type === 'function';
          const isTrigger = node.type === 'trigger';
          const isTable = node.type === 'table';
          const isColumn = node.type === 'column';
          
          return (
            <div
              key={`${node.type}:${node.name}`}
              className="procedure-card"
              style={{ 
                position: 'absolute',
                left: node.x, 
                top: node.y, 
                width: isColumn ? 220 : node.width,
                height: isColumn ? undefined : node.height,
                backgroundColor: theme === 'dark' ? '#1f2937' : '#ffffff',
                borderRadius: '8px',
                boxShadow: isSelected ? '0 0 20px rgba(59, 130, 246, 0.5)' : '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
                border: isSelected ? '2px solid #3b82f6' : '2px solid #e5e7eb',
                transition: 'all 0.35s',
                overflow: 'visible',
                boxSizing: 'border-box'
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: isColumn ? '8px 10px' : (isExpanded ? '14px 16px' : '12px 16px'),
                  borderRadius: isColumn ? '8px' : (isExpanded ? '8px 8px 0 0' : '8px'),
                  cursor: 'pointer',
                  background: isColumn
                    ? 'linear-gradient(135deg, #374151, #6b7280)'
                    : isTable
                    ? 'linear-gradient(135deg, #374151, #4b5563)'
                    : isTrigger
                    ? 'linear-gradient(135deg, #dc2626, #ef4444)'
                    : isFunction
                    ? 'linear-gradient(135deg, #7c3aed, #8b5cf6)'
                    : 'linear-gradient(135deg, #059669, #10b981)',
                  boxShadow: 'inset 0 1px 0 rgba(255, 255, 255, 0.1)',
                  borderBottom: isExpanded ? '1px solid rgba(255, 255, 255, 0.1)' : 'none'
                }}
                onClick={() => !isColumn && toggleProcedure(node.name)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, minWidth: 0 }}>
                  {!isColumn && (<button style={{ 
                    background: 'transparent', 
                    border: 'none', 
                    color: 'white',
                    cursor: 'pointer',
                    padding: '4px'
                  }}>
                    {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </button>)}
                  <Database size={16} style={{ flexShrink: 0, color: 'white' }} />
                  <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, flex: 1 }}>
                    <span style={{ 
                      fontSize: '11px', 
                      color: 'rgba(255, 255, 255, 0.8)', 
                      fontWeight: 500,
                      textTransform: 'uppercase'
                    }}>{toDisplay(node.schema)}</span>
                    <span style={{ 
                      fontSize: isColumn ? '13px' : (isExpanded ? '15px' : '14px'), 
                      fontWeight: isColumn ? 600 : (isExpanded ? 700 : 600), 
                      color: 'white', 
                      overflow: 'hidden', 
                      textOverflow: 'ellipsis', 
                      whiteSpace: 'nowrap'
                    }}>{toDisplay(node.nodeName)}</span>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div style={{
                    fontSize: '10px',
                    padding: '4px 8px',
                    borderRadius: '6px',
                    backgroundColor: 'rgba(255, 255, 255, 0.15)',
                    color: 'white',
                    fontWeight: 600,
                    textTransform: 'uppercase'
                  }}>
                    {isColumn ? 'Col' : isTable ? 'Table' : isFunction ? 'Func' : 'Proc'}
                  </div>
                </div>
              </div>

              {!isColumn && isExpanded && (
                <div style={{ padding: `${nodePadding}px`, paddingBottom: `${nodePadding + 15}px` }}>
                  {isTable && Array.isArray(node.columns) && (
                    <div style={{ marginBottom: '8px' }}>
                      <div style={{ fontSize: '10px', color: theme === 'dark' ? '#9ca3af' : '#6b7280', marginBottom: '6px', fontWeight: 600 }}>Columns</div>
                      {node.columns.length === 0 ? (
                        <div style={{ textAlign: 'center', color: '#9ca3af', fontSize: '12px', padding: '8px' }}>No columns</div>
                      ) : (
                        node.columns.map((col, idx) => (
                          <div key={idx} style={{
                            display: 'flex', alignItems: 'center', gap: '8px',
                            padding: '6px 10px', borderRadius: '4px', marginBottom: '6px',
                            backgroundColor: theme === 'dark' ? '#111827' : '#f3f4f6',
                            border: `1px solid ${theme === 'dark' ? '#1f2937' : '#e5e7eb'}`
                          }}
                          onMouseEnter={() => {
                            const flows = [];
                            if (col.isRead) flows.push({ kind: 'read', tableName: node.name, columnName: col.name });
                            if (col.isWrite) flows.push({ kind: 'write', tableName: node.name, columnName: col.name });
                            if (col.isUpdate) flows.push({ kind: 'update', tableName: node.name, columnName: col.name });
                            setHoveredProcConnections(flows);
                          }}
                          onMouseLeave={() => setHoveredProcConnections([])}
                          >
                            <span style={{ fontFamily: 'monospace', flex: 1, color: theme === 'dark' ? '#e5e7eb' : '#111827' }}>{col.name}</span>
                            {col.isRead && (
                              <span style={{ fontSize: '10px', background: '#10b981', color: 'white', padding: '2px 6px', borderRadius: '3px' }}>READ</span>
                            )}
                            {col.isWrite && (
                              <span style={{ fontSize: '10px', background: '#f59e0b', color: 'white', padding: '2px 6px', borderRadius: '3px' }}>WRITE</span>
                            )}
                            {col.isUpdate && (
                              <span style={{ fontSize: '10px', background: '#fbbf24', color: '#1f2937', padding: '2px 6px', borderRadius: '3px' }}>UPDATE</span>
                            )}
                          </div>
                        ))
                      )}
                    </div>
                  )}
                  {node.parameters && node.parameters.length > 0 && (
                    <div style={{ marginBottom: '8px' }}>
                      <div style={{ fontSize: '10px', color: theme === 'dark' ? '#9ca3af' : '#6b7280', marginBottom: '4px', fontWeight: 600 }}>Parameters</div>
                      {node.parameters.map((param, idx) => (
                        <div key={idx} style={{ fontSize: '12px', color: theme === 'dark' ? '#e5e7eb' : '#111827', padding: '4px 8px', marginBottom: '2px' }}>
                          {param.name}: {param.data_type} {param.is_output ? '(OUT)' : ''}
                        </div>
                      ))}
                    </div>
                  )}
                  {node.reads_tables && node.reads_tables.length > 0 && (
                    <div style={{ marginBottom: '8px' }}>
                      <div style={{ fontSize: '10px', color: theme === 'dark' ? '#9ca3af' : '#6b7280', marginBottom: '4px', fontWeight: 600 }}>Reads Tables</div>
                      {node.reads_tables.map((tbl, idx) => (
                        <div key={idx} style={{ fontSize: '12px', color: '#10b981', padding: '4px 8px', marginBottom: '2px' }}>
                          {tbl}
                        </div>
                      ))}
                    </div>
                  )}
                  {node.writes_tables && node.writes_tables.length > 0 && (
                    <div style={{ marginBottom: '8px' }}>
                      <div style={{ fontSize: '10px', color: theme === 'dark' ? '#9ca3af' : '#6b7280', marginBottom: '4px', fontWeight: 600 }}>Writes Tables</div>
                      {node.writes_tables.map((tbl, idx) => (
                        <div key={idx} style={{ fontSize: '12px', color: '#f59e0b', padding: '4px 8px', marginBottom: '2px' }}>
                          {tbl}
                        </div>
                      ))}
                    </div>
                  )}
                  {node.calls_procedures && node.calls_procedures.length > 0 && (
                    <div style={{ marginBottom: '8px' }}>
                      <div style={{ fontSize: '10px', color: theme === 'dark' ? '#9ca3af' : '#6b7280', marginBottom: '4px', fontWeight: 600 }}>Calls Procedures</div>
                      {node.calls_procedures.map((proc, idx) => (
                        <div key={idx} style={{ fontSize: '12px', color: '#3b82f6', padding: '4px 8px', marginBottom: '2px' }}>
                          {proc}
                        </div>
                      ))}
                    </div>
                  )}
                  {node.called_by && node.called_by.length > 0 && (
                    <div>
                      <div style={{ fontSize: '10px', color: theme === 'dark' ? '#9ca3af' : '#6b7280', marginBottom: '4px', fontWeight: 600 }}>Called By</div>
                      {node.called_by.map((caller, idx) => (
                        <div key={idx} style={{ fontSize: '12px', color: '#3b82f6', padding: '4px 8px', marginBottom: '2px' }}>
                          {caller}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  // Loading screen component
  const renderLoadingScreen = () => {
    return (
      <div style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(11, 15, 20, 0.95)',
        backdropFilter: 'blur(10px)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 10000,
        color: 'white'
      }}>
        <Loader2 size={64} style={{ animation: 'spin 1s linear infinite', marginBottom: '24px' }} />
        <h2 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '8px' }}>
          Analyzing codebase using {useOpenAI && openAIKey ? 'OpenAI' : 'Ollama'}
        </h2>
        <p style={{ fontSize: '16px', color: '#9ca3af' }}>Please wait while we process your SQL scripts...</p>
        <style>{`
          @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    );
  };

  // Error screen component
  const renderErrorScreen = () => {
    if (!analysisError) return null;
    return (
      <div style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(11, 15, 20, 0.95)',
        backdropFilter: 'blur(10px)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 10001,
        color: 'white',
        padding: '24px'
      }}>
        <div style={{
          background: '#1f2937',
          borderRadius: '12px',
          padding: '32px',
          maxWidth: '600px',
          width: '100%',
          border: '1px solid #ef4444',
          boxShadow: '0 25px 50px -12px rgba(239, 68, 68, 0.25)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
            <AlertCircle size={32} color="#ef4444" />
            <h2 style={{ fontSize: '24px', fontWeight: 700, margin: 0, color: '#ef4444' }}>
              Analysis Failed
            </h2>
          </div>
          <div style={{
            background: '#0b0f14',
            borderRadius: '8px',
            padding: '16px',
            marginBottom: '24px',
            border: '1px solid #374151',
            fontFamily: 'monospace',
            fontSize: '14px',
            color: '#fca5a5',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            maxHeight: '300px',
            overflow: 'auto'
          }}>
            {analysisError}
          </div>
          <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
            <button
              onClick={() => {
                setAnalysisError(null);
                setShowStart(true);
              }}
              style={{
                padding: '10px 20px',
                background: '#374151',
                color: 'white',
                border: '1px solid #4b5563',
                borderRadius: '8px',
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: 600,
                transition: 'all 0.2s'
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = '#4b5563'}
              onMouseLeave={(e) => e.currentTarget.style.background = '#374151'}
            >
              Go Back
            </button>
            <button
              onClick={() => setAnalysisError(null)}
              style={{
                padding: '10px 20px',
                background: '#ef4444',
                color: 'white',
                border: 'none',
                borderRadius: '8px',
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: 600,
                transition: 'all 0.2s'
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = '#dc2626'}
              onMouseLeave={(e) => e.currentTarget.style.background = '#ef4444'}
            >
              Dismiss
            </button>
          </div>
        </div>
      </div>
    );
  };

  // LLM Info Modal
  const renderLLMInfoModal = () => {
    if (!showLLMInfo || !selectedLLMInfo) return null;
    return (
      <div
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.8)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 10001,
          padding: '20px'
        }}
        onClick={() => setShowLLMInfo(false)}
      >
        <div
          style={{
            background: theme === 'dark' ? '#1f2937' : '#ffffff',
            borderRadius: '12px',
            width: '90%',
            maxWidth: '1200px',
            maxHeight: '90vh',
            display: 'flex',
            flexDirection: 'column',
            boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
            overflow: 'hidden'
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '20px 24px',
            borderBottom: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`,
            background: theme === 'dark' ? '#111827' : '#f9fafb'
          }}>
            <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 700, color: theme === 'dark' ? 'white' : '#111827' }}>
              LLM Analysis Details: {selectedLLMInfo.name}
            </h2>
            <button
              onClick={() => setShowLLMInfo(false)}
              style={{
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                color: theme === 'dark' ? '#9ca3af' : '#6b7280',
                padding: '4px',
                display: 'flex',
                alignItems: 'center'
              }}
            >
              <X size={24} />
            </button>
          </div>
          <div style={{
            display: 'grid',
            gridTemplateColumns: selectedLLMInfo.prompt ? '1fr 1fr 1fr' : '1fr 1fr',
            gap: '24px',
            padding: '24px',
            overflow: 'auto',
            flex: 1
          }}>
            {/* SQL Code Box */}
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '12px'
            }}>
              <h3 style={{
                margin: 0,
                fontSize: '16px',
                fontWeight: 600,
                color: theme === 'dark' ? 'white' : '#111827',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}>
                <File size={18} />
                SQL Code
              </h3>
              <div style={{
                background: theme === 'dark' ? '#0b0f14' : '#f3f4f6',
                borderRadius: '8px',
                padding: '16px',
                border: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`,
                maxHeight: '400px',
                overflow: 'auto',
                fontFamily: 'monospace',
                fontSize: '13px',
                lineHeight: '1.6',
                color: theme === 'dark' ? '#e5e7eb' : '#111827',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word'
              }}>
                {selectedLLMInfo.sql || 'No SQL code available'}
              </div>
            </div>
            {/* LLM Prompt Box - Show if available */}
            {selectedLLMInfo.prompt && (
              <div style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '12px'
              }}>
                <h3 style={{
                  margin: 0,
                  fontSize: '16px',
                  fontWeight: 600,
                  color: theme === 'dark' ? 'white' : '#111827',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px'
                }}>
                  <Info size={18} />
                  LLM Prompt
                </h3>
                <div style={{
                  background: theme === 'dark' ? '#0b0f14' : '#f3f4f6',
                  borderRadius: '8px',
                  padding: '16px',
                  border: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`,
                  maxHeight: '400px',
                  overflow: 'auto',
                  fontFamily: 'monospace',
                  fontSize: '12px',
                  lineHeight: '1.6',
                  color: theme === 'dark' ? '#e5e7eb' : '#111827',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word'
                }}>
                  {selectedLLMInfo.prompt}
                </div>
              </div>
            )}
            {/* LLM Response Box */}
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '12px'
            }}>
              <h3 style={{
                margin: 0,
                fontSize: '16px',
                fontWeight: 600,
                color: theme === 'dark' ? 'white' : '#111827',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}>
                <Database size={18} />
                LLM Response
              </h3>
              <div style={{
                background: theme === 'dark' ? '#0b0f14' : '#f3f4f6',
                borderRadius: '8px',
                padding: '16px',
                border: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`,
                maxHeight: '400px',
                overflow: 'auto',
                fontFamily: 'monospace',
                fontSize: '13px',
                lineHeight: '1.6',
                color: theme === 'dark' ? '#e5e7eb' : '#111827',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word'
              }}>
                {selectedLLMInfo.response ? (
                  <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {typeof selectedLLMInfo.response === 'string' 
                      ? selectedLLMInfo.response 
                      : JSON.stringify(selectedLLMInfo.response, null, 2)}
                  </pre>
                ) : 'No response available'}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderLineageNotice = () => {
    if (!lineageNotice || showStart) return null;
    return (
      <div
        style={{
          position: 'fixed',
          top: '90px',
          left: '50%',
          transform: 'translateX(-50%)',
          background: 'rgba(59,130,246,0.12)',
          color: '#bfdbfe',
          border: '1px solid rgba(59,130,246,0.35)',
          borderRadius: '10px',
          padding: '12px 18px',
          display: 'flex',
          gap: '10px',
          alignItems: 'center',
          zIndex: 2000,
          maxWidth: '640px',
          width: 'calc(100% - 48px)',
          boxShadow: '0 10px 30px rgba(15,23,42,0.3)',
          backdropFilter: 'blur(10px)'
        }}
      >
        <Info size={18} color="#93c5fd" />
        <span style={{ fontSize: '14px', lineHeight: 1.5 }}>{lineageNotice}</span>
      </div>
    );
  };

  const toastNode = renderToast();

  if (isAnalyzing) {
    return (
      <>
        {toastNode}
        {renderLoadingScreen()}
      </>
    );
  }

  if (showStart) {
   // Dedicated connection form for dialect-specific settings
   if (showConnectionForm) {
     const isSnowflake = selectedDialect === 'snowflake';
     const isTeradata = selectedDialect === 'teradata';
     const isPostgres = ['postgres', 'postgresql', 'postgress', 'pgsql'].includes((selectedDialect || '').toLowerCase());
     const isOracle = (selectedDialect || '').toLowerCase() === 'oracle';
     return (
       <>
        {toastNode}
        {isSnowflake ? (
          <SnowflakeConnectionForm
            connectionDetails={connectionDetails}
            setConnectionDetails={setConnectionDetails}
            onBack={handleConnectionBack}
            onRunAnalysis={handleSnowflakeMetadataAnalysis}
            useOpenAI={useOpenAI}
            setUseOpenAI={setUseOpenAI}
            openAIKey={openAIKey}
            setOpenAIKey={setOpenAIKey}
          />
        ) : isTeradata ? (
          <TeradataConnectionForm
            connectionDetails={connectionDetails}
            setConnectionDetails={setConnectionDetails}
            onBack={handleConnectionBack}
            onFetchMetadata={handleFetchMetadata}
            onProceed={handleMetadataProceed}
            metadataFetched={metadataFetched}
            isSubmitting={isConnectionSubmitting}
            useOpenAI={useOpenAI}
            setUseOpenAI={setUseOpenAI}
            openAIKey={openAIKey}
            setOpenAIKey={setOpenAIKey}
          />
        ) : isPostgres ? (
          <PostgresConnectionForm
            connectionDetails={connectionDetails}
            setConnectionDetails={setConnectionDetails}
            onBack={handleConnectionBack}
            onFetchMetadata={handleFetchMetadata}
            onProceed={handleMetadataProceed}
            metadataFetched={metadataFetched}
            isSubmitting={isConnectionSubmitting}
            useOpenAI={useOpenAI}
            setUseOpenAI={setUseOpenAI}
            openAIKey={openAIKey}
            setOpenAIKey={setOpenAIKey}
          />
        ) : isOracle ? (
          <OracleConnectionForm
            connectionDetails={connectionDetails}
            setConnectionDetails={setConnectionDetails}
            onBack={handleConnectionBack}
            onFetchMetadata={handleFetchMetadata}
            onProceed={handleMetadataProceed}
            metadataFetched={metadataFetched}
            isSubmitting={isConnectionSubmitting}
            useOpenAI={useOpenAI}
            setUseOpenAI={setUseOpenAI}
            openAIKey={openAIKey}
            setOpenAIKey={setOpenAIKey}
          />
        ) : (
          <TsqlConnectionForm
            connectionDetails={connectionDetails}
            setConnectionDetails={setConnectionDetails}
            onBack={handleConnectionBack}
            onFetchMetadata={handleFetchMetadata}
            onProceed={handleMetadataProceed}
            metadataFetched={metadataFetched}
            isSubmitting={isConnectionSubmitting}
            useOpenAI={useOpenAI}
            setUseOpenAI={setUseOpenAI}
            openAIKey={openAIKey}
            setOpenAIKey={setOpenAIKey}
          />
        )}
        {!(isSnowflake || isTeradata || isPostgres || isOracle) && (
          <input
            ref={folderInputRef}
            type="file"
            style={{ display: 'none' }}
            multiple
            onChange={async (e) => {
              const files = Array.from(e.target.files || []);
              if (files.length === 0) {
                if (useEnhancedFlow) setUseEnhancedFlow(false);
                return;
              }
              try {
                setShowStart(false);
                await uploadFolderToServer(files);
              } catch (err) {
                console.error(err);
              } finally {
                if (folderInputRef.current) {
                  folderInputRef.current.value = '';
                }
                setScriptSelectionMode('folder');
                setUseEnhancedFlow(false);
                setShowDialectPicker(false);
                setShowConnectionForm(false);
              }
            }}
          />
        )}
       </>
     );
   }
  // Dedicated Dialect Picker Page
  const resolveDialect = (key) => key;

  if (showDialectPicker) {
    const scriptOptions = [
      { key: 'tsql', label: 'T-SQL', img: 'https://cdn.jsdelivr.net/npm/simple-icons@v11/icons/microsoftsqlserver.svg' },
      { key: 'snowflake', label: 'Snowflake', img: 'https://upload.wikimedia.org/wikipedia/commons/f/ff/Snowflake_Logo.svg' },
      { key: 'teradata', label: 'Teradata', img: 'https://upload.wikimedia.org/wikipedia/commons/c/cd/Teradata_logo_2018.svg' },
      { key: 'oracle', label: 'Oracle', img: 'https://upload.wikimedia.org/wikipedia/commons/5/50/Oracle_logo.svg' },
      { key: 'postgres', label: 'PostgreSQL', img: 'https://upload.wikimedia.org/wikipedia/commons/2/29/Postgresql_elephant.svg' },
      { key: 'mysql', label: 'MySQL', img: 'https://upload.wikimedia.org/wikipedia/en/d/dd/MySQL_logo.svg' },
      { key: 'sqlite', label: 'SQLite', img: 'https://upload.wikimedia.org/wikipedia/commons/3/38/SQLite370.svg' },
    ];
    const isCodebase = pendingAction === 'codebase';
    return (
      <>
        {toastNode}
        {isCodebase ? (
          <DialectPickerCodebase
            onBack={() => { setShowDialectPicker(false); setPendingAction(null); }}
            onSelect={(opt) => {
              const resolvedDialect = resolveDialect(opt.key);
              setSelectedDialect(resolvedDialect);
              setUseEnhancedFlow(false);
              setMetadataFetched(false);
              setScriptSelectionMode('folder');
              if (['tsql', 'snowflake', 'teradata', 'postgres', 'oracle'].includes(resolvedDialect)) {
                setShowConnectionForm(true);
                return;
              }
              openFilePicker('folder');
            }}
          />
        ) : (
          <DialectPicker
            options={scriptOptions}
            onBack={() => { setShowDialectPicker(false); setPendingAction(null); }}
            onSelect={(opt) => {
              const resolvedDialect = resolveDialect(opt.key);
              setSelectedDialect(resolvedDialect);
              setUseEnhancedFlow(false);
              setMetadataFetched(false);
              openFilePicker('folder');
            }}
            useOpenAI={useOpenAI}
            setUseOpenAI={setUseOpenAI}
            openAIKey={openAIKey}
            setOpenAIKey={setOpenAIKey}
          />
        )}
        <input
          ref={folderInputRef}
          type="file"
          style={{ display: 'none' }}
          multiple
          onChange={async (e) => {
            const files = Array.from(e.target.files || []);
            if (files.length === 0) {
              if (useEnhancedFlow) setUseEnhancedFlow(false);
              return;
            }
            try {
              setShowStart(false);
              await uploadFolderToServer(files);
            } catch (err) {
              console.error(err);
            } finally {
              if (folderInputRef.current) {
                folderInputRef.current.value = '';
              }
              setScriptSelectionMode('folder');
              setUseEnhancedFlow(false);
              setMetadataFetched(false);
              setShowDialectPicker(false);
            }
          }}
        />
      </>
    );
  }

    return (
      <>
        {toastNode}
        {renderErrorScreen()}
        {renderLLMInfoModal()}
        {renderLineageNotice()}
        <div style={{ display: 'flex', minHeight: '100vh', background: '#0b0f14', color: 'white' }}>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
          <div style={{ maxWidth: '900px', width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '28px' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ display: 'inline-flex', alignItems: 'center', gap: '10px', padding: '10px 14px', borderRadius: '9999px', background: 'rgba(37, 99, 235, 0.12)', border: '1px solid rgba(59, 130, 246, 0.25)', fontSize: '12px', letterSpacing: '0.4px' }}>
                <Database size={16} />
                <span>SQL Lineage Tool</span>
              </div>
              <h1 style={{ margin: '16px 0 8px', fontSize: '28px' }}>Choose how you want to start</h1>
              <p style={{ margin: 0, color: '#9ca3af' }}>Analyze your SQL scripts or scan a codebase for lineage insights</p>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '20px', width: '100%', maxWidth: '900px' }}>
              <button
                onClick={handleAnalyzeScript}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'flex-start',
                  justifyContent: 'center',
                  gap: '10px',
                  padding: '24px',
                  width: '100%',
                  minHeight: '140px',
                  background: 'linear-gradient(135deg, #dc2626, #ef4444)',
                  color: 'white',
                  border: '1px solid #b91c1c',
                  borderRadius: '14px',
                  cursor: 'pointer',
                  boxShadow: '0 20px 40px rgba(220, 38, 38, 0.25)',
                  transition: 'transform 0.25s ease, box-shadow 0.25s ease, filter 0.25s ease'
                }}
                onMouseEnter={(e) => { e.currentTarget.style.transform = 'translateY(-4px)'; e.currentTarget.style.boxShadow = '0 25px 50px rgba(220, 38, 38, 0.35)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.transform = 'translateY(0px)'; e.currentTarget.style.boxShadow = '0 20px 40px rgba(220, 38, 38, 0.25)'; }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontWeight: 700, fontSize: '18px' }}>
                  <File size={18} />
                  Analyze Stored SQL Files
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', opacity: 0.9, fontSize: '12px' }}>
                  Analyze SQL scripts from a selected folder (Static Lineage)
                </div>
              </button>

              <button
                onClick={handleStartAnalyzeCodebase}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'flex-start',
                  justifyContent: 'center',
                  gap: '10px',
                  padding: '24px',
                  width: '100%',
                  minHeight: '140px',
                  background: 'linear-gradient(135deg, #059669, #10b981)',
                  color: 'white',
                  border: '1px solid #047857',
                  borderRadius: '14px',
                  cursor: 'pointer',
                  boxShadow: '0 20px 40px rgba(16, 185, 129, 0.22)',
                  transition: 'transform 0.25s ease, box-shadow 0.25s ease, filter 0.25s ease'
                }}
                onMouseEnter={(e) => { e.currentTarget.style.transform = 'translateY(-4px)'; e.currentTarget.style.boxShadow = '0 25px 50px rgba(16, 185, 129, 0.3)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.transform = 'translateY(0px)'; e.currentTarget.style.boxShadow = '0 20px 40px rgba(16, 185, 129, 0.22)'; }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontWeight: 700, fontSize: '18px' }}>
                  <Database size={18} />
                  Analyze Live Database
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', opacity: 0.9, fontSize: '12px' }}>
                  Analyze the database schema via direct connection (Dynamic Lineage).
                </div>
              </button>
            </div>
          </div>
        </div>
        {/* Hidden folder input for directory selection */}
        <input
          ref={folderInputRef}
          type="file"
          style={{ display: 'none' }}
          multiple
          onChange={async (e) => {
            const files = Array.from(e.target.files || []);
            if (files.length === 0) {
              if (useEnhancedFlow) setUseEnhancedFlow(false);
              return;
            }
            try {
              setShowStart(false);
              await uploadFolderToServer(files);
            } catch (err) {
              console.error(err);
            } finally {
              if (folderInputRef.current) {
                folderInputRef.current.value = '';
              }
              setScriptSelectionMode('folder');
              setUseEnhancedFlow(false);
              setMetadataFetched(false);
            }
          }}
        />
        {/* Zip input removed */}
      </div>
      </>
    );
  }

  return (
    <>
      {toastNode}
      <div style={{ display: 'flex', height: '100vh', backgroundColor: theme === 'dark' ? '#0b0f14' : '#f7f7f5', color: theme === 'dark' ? 'white' : '#111827' }}>
      {/* Left Sidebar */}
      <div style={{ width: '320px', borderRight: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`, backgroundColor: theme === 'dark' ? '#1f2937' : '#ffffff', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '16px', borderBottom: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}` }}>
          <h1 style={{ fontSize: '18px', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
            <Database size={20} />
            SQL Lineage Analyzer
          </h1>
          <p style={{ fontSize: '12px', color: theme === 'dark' ? '#9ca3af' : '#6b7280', marginTop: '4px' }}>AST-based parsing</p>
        </div>

        
        
        <div style={{ padding: '16px', borderBottom: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}` }}>
          
          <button
            onClick={() => {
              setUseEnhancedFlow(false);
              setMetadataFetched(false);
              openFilePicker('folder');
            }}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              padding: '8px 16px',
              backgroundColor: theme === 'dark' ? '#059669' : '#10b981',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '14px',
              fontWeight: 500,
              transition: 'background-color 0.35s',
              marginTop: '8px'
            }}
          >
            <Database size={16} />
            <span>Analyze Folder…</span>
          </button>
          {/* Zip analyze button removed */}
        </div>


        {parseErrors.length > 0 && (
          <div style={{ padding: '16px', borderBottom: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`, backgroundColor: theme === 'dark' ? '#7f1d1d' : '#fee2e2' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <AlertCircle size={16} color={theme === 'dark' ? '#fca5a5' : '#b91c1c'} />
              <span style={{ fontSize: '12px', fontWeight: 600, color: theme === 'dark' ? '#fca5a5' : '#b91c1c' }}>Parse Errors ({parseErrors.length})</span>
            </div>
            <div style={{ maxHeight: '150px', overflowY: 'auto' }}>
              {parseErrors.map((err, idx) => (
                <div key={idx} style={{ fontSize: '11px', color: theme === 'dark' ? '#fecaca' : '#991b1b', marginBottom: '4px' }}>
                  <strong>{err.file}:</strong> {err.error}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* JSON File Information */}
        {lineageReport && (
          <div style={{ padding: '16px', borderBottom: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}` }}>
            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '8px', 
              padding: '12px', 
              backgroundColor: theme === 'dark' ? '#374151' : '#f3f4f6', 
              borderRadius: '6px'
            }}>
              <File size={16} style={{ color: theme === 'dark' ? '#60a5fa' : '#2563eb', flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: '14px', fontWeight: 600, color: theme === 'dark' ? '#e5e7eb' : '#111827' }}>
                  Statement lineage (loaded)
                </div>
                <div style={{ fontSize: '12px', color: theme === 'dark' ? '#9ca3af' : '#6b7280' }}>
                  Dialect: {lineageReport.metadata?.dialect || 'Unknown'} | 
                  Tables: {lineageReport.summary?.total_tables || 0} | 
                  Columns: {lineageReport.summary?.total_columns || 0}
                </div>
              </div>
            </div>
          </div>
        )}

        <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>

          {/* Table List Panel - Show all tables for clicking (hidden on Executable Components tab) */}
          {lineageData && !showProceduresSection && (
            <div style={{ marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                <h4 style={{ fontSize: '12px', fontWeight: 600, color: theme === 'dark' ? '#9ca3af' : '#6b7280', textTransform: 'uppercase', margin: 0 }}>
                  All Tables (Click to Focus)
                </h4>
                {focusedTable && (
                  <button
                    onClick={clearFocus}
                    style={{
                      fontSize: '10px',
                      padding: '2px 6px',
                      backgroundColor: theme === 'dark' ? '#374151' : '#e5e7eb',
                      color: theme === 'dark' ? '#e5e7eb' : '#374151',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: 'pointer'
                    }}
                  >
                    Clear Focus
                  </button>
                )}
              </div>
              <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                <input
                  type="text"
                  placeholder="Search tables"
                  value={tableSearch}
                  onChange={(e) => setTableSearch(e.target.value)}
                  style={{
                    flex: 1,
                    fontSize: '12px',
                    padding: '6px 8px',
                    borderRadius: '6px',
                    border: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`,
                    backgroundColor: theme === 'dark' ? '#111827' : '#ffffff',
                    color: theme === 'dark' ? '#e5e7eb' : '#111827'
                  }}
                />
                {tableSearch && (
                  <button
                    onClick={() => setTableSearch('')}
                    style={{
                      fontSize: '12px',
                      padding: '6px 8px',
                      borderRadius: '6px',
                      border: 'none',
                      backgroundColor: theme === 'dark' ? '#374151' : '#e5e7eb',
                      color: theme === 'dark' ? '#e5e7eb' : '#374151',
                      cursor: 'pointer'
                    }}
                  >
                    Clear
                  </button>
                )}
              </div>
              <div style={{ height: '100%', overflowY: 'auto', border: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`, borderRadius: '6px' }}>
                {(() => {
                  const baseTables = lineageData.tables.filter(table => table.columns && table.columns.length > 0);
                  const filteredTables = baseTables.filter(table => {
                    const fullName = `${table.schema || ''}.${table.tableName || ''}`;
                    return fuzzyMatch(tableSearch, table.tableName)
                      || fuzzyMatch(tableSearch, table.schema)
                      || fuzzyMatch(tableSearch, table.name)
                      || fuzzyMatch(tableSearch, fullName);
                  });
                  const listToRender = tableSearch ? filteredTables : baseTables;
                  if (tableSearch && listToRender.length === 0) {
                    return (
                      <div style={{ padding: '12px', fontSize: '12px', color: theme === 'dark' ? '#9ca3af' : '#6b7280' }}>
                        No tables match "{tableSearch}".
                      </div>
                    );
                  }
                  return listToRender.map((table) => {
                    const isFocused = focusedTable === table.name;
                    const isConnected = focusedTableConnections.has(table.name);
                    const isVisible = !focusedTable || isConnected;
                    const hasConnections = lineageData.connections.some(conn => 
                      conn.sourceTable === table.name || conn.targetTable === table.name
                    );
                    
                    return (
                      <div
                        key={table.name}
                        onClick={() => focusOnTable(table.name)}
                        style={{
                          padding: '8px 12px',
                          cursor: 'pointer',
                          borderBottom: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`,
                          backgroundColor: isFocused 
                            ? (theme === 'dark' ? '#1d4ed8' : '#dbeafe')
                            : isConnected && focusedTable
                            ? (theme === 'dark' ? '#374151' : '#f3f4f6')
                            : 'transparent',
                          opacity: isVisible ? 1 : 0.3,
                          transition: 'all 0.2s ease',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px'
                        }}
                        onMouseEnter={(e) => {
                          if (isVisible) {
                            e.currentTarget.style.backgroundColor = isFocused 
                              ? (theme === 'dark' ? '#2563eb' : '#bfdbfe')
                              : (theme === 'dark' ? '#4b5563' : '#e5e7eb');
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (isVisible) {
                            e.currentTarget.style.backgroundColor = isFocused 
                              ? (theme === 'dark' ? '#1d4ed8' : '#dbeafe')
                              : isConnected && focusedTable
                              ? (theme === 'dark' ? '#374151' : '#f3f4f6')
                              : 'transparent';
                          }
                        }}
                      >
                        <div style={{ 
                          width: '8px', 
                          height: '8px', 
                          borderRadius: '50%', 
                          backgroundColor: isFocused 
                            ? '#3b82f6' 
                            : isConnected && focusedTable
                            ? '#10b981'
                            : hasConnections
                            ? '#f59e0b'
                            : '#6b7280',
                          flexShrink: 0
                        }}></div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ 
                            fontSize: '12px', 
                            color: theme === 'dark' ? '#9ca3af' : '#6b7280',
                            fontWeight: 500,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap'
                          }}>
                            {table.schema}
                          </div>
                          <div style={{ 
                            fontSize: '13px', 
                            fontWeight: 600,
                            color: theme === 'dark' ? '#e5e7eb' : '#111827',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap'
                          }}>
                            {table.tableName}
                          </div>
                        </div>
                        <div style={{
                          fontSize: '10px',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          backgroundColor: table.type === 'target' 
                            ? '#2563eb' 
                            : table.type === 'source' 
                            ? '#4b5563' 
                            : '#10b981',
                          color: 'white',
                          fontWeight: 600,
                          textTransform: 'uppercase'
                        }}>
                          {table.type === 'target' ? 'T' : table.type === 'source' ? 'S' : 'V'}
                        </div>
                      </div>
                    );
                  });
                })()}
              </div>
              {focusedTable && (
                <div style={{ 
                  marginTop: '8px', 
                  padding: '8px', 
                  backgroundColor: theme === 'dark' ? '#1d4ed8' : '#dbeafe', 
                  borderRadius: '6px',
                  fontSize: '11px',
                  color: theme === 'dark' ? '#bfdbfe' : '#1e40af'
                }}>
                  <div style={{ marginBottom: '8px' }}>
                    <strong>Focus Mode:</strong> Showing {focusedTableConnections.size} connected tables
                  </div>
                  <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                    <button
                      onClick={() => {
                        const connections = lineageData.connections;
                        
                        // Recursively find all connected tables
                        const findAllConnectedTables = (startTable, visited = new Set()) => {
                          if (visited.has(startTable)) return visited;
                          visited.add(startTable);
                          
                          // Find all tables connected to this table
                          connections.forEach(conn => {
                            if (conn.sourceTable === startTable && !visited.has(conn.targetTable)) {
                              findAllConnectedTables(conn.targetTable, visited);
                            }
                            if (conn.targetTable === startTable && !visited.has(conn.sourceTable)) {
                              findAllConnectedTables(conn.sourceTable, visited);
                            }
                          });
                          
                          return visited;
                        };
                        
                        const allConnectedTables = findAllConnectedTables(focusedTable);
                        setFocusedTableConnections(allConnectedTables);
                      }}
                      style={{
                        fontSize: '10px',
                        padding: '4px 8px',
                        backgroundColor: theme === 'dark' ? '#374151' : '#e5e7eb',
                        color: theme === 'dark' ? '#e5e7eb' : '#374151',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer'
                      }}
                    >
                      Expand All
                    </button>
                    <button
                      onClick={() => {
                        // Show only immediate connections
                        const connections = lineageData.connections;
                        const immediateConnections = new Set([focusedTable]);
                        
                        connections
                          .filter(conn => conn.targetTable === focusedTable)
                          .forEach(conn => immediateConnections.add(conn.sourceTable));
                        
                        connections
                          .filter(conn => conn.sourceTable === focusedTable)
                          .forEach(conn => immediateConnections.add(conn.targetTable));
                        
                        setFocusedTableConnections(immediateConnections);
                      }}
                      style={{
                        fontSize: '10px',
                        padding: '4px 8px',
                        backgroundColor: theme === 'dark' ? '#374151' : '#e5e7eb',
                        color: theme === 'dark' ? '#e5e7eb' : '#374151',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer'
                      }}
                    >
                      Immediate Only
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Executable Components search/list (shown only on Executable Components tab) */}
          {showProceduresSection && (
            <div style={{ marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                <h4 style={{ fontSize: '12px', fontWeight: 600, color: theme === 'dark' ? '#9ca3af' : '#6b7280', textTransform: 'uppercase', margin: 0 }}>
                  Executable Components (Click to Select)
                </h4>
              </div>
              <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                <input
                  type="text"
                  placeholder="Search executable components"
                  value={procedureSearch}
                  onChange={(e) => setProcedureSearch(e.target.value)}
                  style={{
                    flex: 1,
                    fontSize: '12px',
                    padding: '6px 8px',
                    borderRadius: '6px',
                    border: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`,
                    backgroundColor: theme === 'dark' ? '#111827' : '#ffffff',
                    color: theme === 'dark' ? '#e5e7eb' : '#111827'
                  }}
                />
                {procedureSearch && (
                  <button
                    onClick={() => setProcedureSearch('')}
                    style={{
                      fontSize: '12px',
                      padding: '6px 8px',
                      borderRadius: '6px',
                      border: 'none',
                      backgroundColor: theme === 'dark' ? '#374151' : '#e5e7eb',
                      color: theme === 'dark' ? '#e5e7eb' : '#374151',
                      cursor: 'pointer'
                    }}
                  >
                    Clear
                  </button>
                )}
              </div>
              <div style={{ height: '100%', overflowY: 'auto', border: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`, borderRadius: '6px' }}>
                {(() => {
                  const procNames = procedureLineage?.procedures ? Object.keys(procedureLineage.procedures) : [];
                  const funcNames = procedureLineage?.functions ? Object.keys(procedureLineage.functions) : [];
                  const triggerNames = procedureLineage?.triggers ? Object.keys(procedureLineage.triggers) : [];
                  const allNames = [...procNames, ...funcNames, ...triggerNames];
                  const filtered = allNames.filter(name => fuzzyMatch(procedureSearch, name));
                  const listToRender = procedureSearch ? filtered : allNames;
                  const dedupedList = Array.from(new Set(listToRender));
                  if (procedureSearch && listToRender.length === 0) {
                    return (
                      <div style={{ padding: '12px', fontSize: '12px', color: theme === 'dark' ? '#9ca3af' : '#6b7280' }}>
                        No executable components match "{procedureSearch}".
                      </div>
                    );
                  }
                  return dedupedList.map((name) => {
                    const isSelected = selectedProcedure === name;
                    const isFunction = procedureLineage?.functions && Object.keys(procedureLineage.functions).includes(name);
                    const isTrigger = procedureLineage?.triggers && Object.keys(procedureLineage.triggers).includes(name);
                    const badgeColor = isTrigger ? '#dc2626' : (isFunction ? '#7c3aed' : '#059669');
                    return (
                      <div
                        key={name}
                        onClick={() => {
                          setSelectedProcedure(name);
                          setIsRightPanelOpen(true); // Open panel when procedure is selected
                        }}
                        style={{
                          padding: '8px 12px',
                          cursor: 'pointer',
                          borderBottom: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`,
                          backgroundColor: isSelected 
                            ? (theme === 'dark' ? '#1d4ed8' : '#dbeafe')
                            : 'transparent',
                          transition: 'all 0.2s ease',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px'
                        }}
                      >
                        <div style={{ 
                          width: '8px', 
                          height: '8px', 
                          borderRadius: '50%', 
                          backgroundColor: badgeColor,
                          flexShrink: 0
                        }}></div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ 
                            fontSize: '13px', 
                            fontWeight: 600,
                            color: theme === 'dark' ? '#e5e7eb' : '#111827',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap'
                          }}>
                            {name}
                          </div>
                        </div>
                        <div style={{
                          fontSize: '10px',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          backgroundColor: badgeColor,
                          color: 'white',
                          fontWeight: 600,
                          textTransform: 'uppercase'
                        }}>
                          {isTrigger ? 'T' : (isFunction ? 'F' : 'P')}
                        </div>
                      </div>
                    );
                  });
                })()}
              </div>
            </div>
          )}


          {lineageReport ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>

              {false && (
                <div style={{ padding: '8px', color: theme === 'dark' ? '#d1d5db' : '#374151', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div>
                    <div style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', opacity: 0.7, marginBottom: '6px' }}>Procedures</div>
                    {(procedureLineage?.procedures && Object.keys(procedureLineage.procedures).length > 0) ? (
                      <ul style={{ paddingLeft: '16px' }}>
                        {Object.keys(procedureLineage.procedures).map((proc) => (
                          <li key={proc} style={{ marginBottom: '6px' }}>{proc}</li>
                        ))}
                      </ul>
                    ) : (
                      <div style={{ fontSize: '12px', color: theme === 'dark' ? '#9ca3af' : '#6b7280' }}>No procedures found</div>
                    )}
                  </div>
                  <div>
                    <div style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', opacity: 0.7, marginBottom: '6px' }}>Functions</div>
                    {(procedureLineage?.functions && Object.keys(procedureLineage.functions).length > 0) ? (
                      <ul style={{ paddingLeft: '16px' }}>
                        {Object.keys(procedureLineage.functions).map((fn) => (
                          <li key={fn} style={{ marginBottom: '6px' }}>{fn}</li>
                        ))}
                      </ul>
                    ) : (
                      <div style={{ fontSize: '12px', color: theme === 'dark' ? '#9ca3af' : '#6b7280' }}>
                        {`No functions found${procedureLineage?.summary ? ` (Scalar: ${procedureLineage.summary.scalar_functions || 0}, Table-valued: ${procedureLineage.summary.table_valued_functions || 0})` : ''}`}
                      </div>
                    )}
                  </div>
                  <div>
                    <div style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', opacity: 0.7, marginBottom: '6px' }}>UDFs</div>
                    {(procedureLineage?.functions && Object.keys(procedureLineage.functions).length > 0) ? (
                      <ul style={{ paddingLeft: '16px' }}>
                        {Object.keys(procedureLineage.functions).map((fn) => (
                          <li key={fn} style={{ marginBottom: '6px' }}>{fn}</li>
                        ))}
                      </ul>
                    ) : (
                      <div style={{ fontSize: '12px', color: theme === 'dark' ? '#9ca3af' : '#6b7280' }}>No UDFs found</div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div style={{ 
              padding: '16px', 
              textAlign: 'center', 
              color: theme === 'dark' ? '#9ca3af' : '#6b7280', 
              fontSize: '12px' 
            }}>
              No lineage report loaded
            </div>
          )}
        </div>

        {lineageReport && (
          <div style={{ padding: '16px', borderTop: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`, backgroundColor: theme === 'dark' ? '#1f2937' : '#ffffff' }}>
            <div style={{ fontSize: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: theme === 'dark' ? '#9ca3af' : '#6b7280' }}>Total Scripts:</span>
                <span style={{ fontWeight: 600 }}>{lineageReport.summary?.total_scripts || summaryReport?.overall_summary?.total_files_analyzed || 0}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: theme === 'dark' ? '#9ca3af' : '#6b7280' }}>Total Tables:</span>
                <span style={{ fontWeight: 600 }}>{lineageReport.summary?.total_tables || summaryReport?.overall_summary?.total_tables || 0}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: theme === 'dark' ? '#9ca3af' : '#6b7280' }}>Total Columns:</span>
                <span style={{ fontWeight: 600 }}>{lineageReport.summary?.total_columns || summaryReport?.overall_summary?.total_columns || 0}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: theme === 'dark' ? '#9ca3af' : '#6b7280' }}>Dependencies:</span>
                <span style={{ fontWeight: 600 }}>{lineageReport.summary?.total_dependencies || summaryReport?.statement_lineage?.total_dependencies || 0}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: theme === 'dark' ? '#9ca3af' : '#6b7280' }}>Circular Deps:</span>
                <span style={{ fontWeight: 600, color: lineageReport.execution_order?.has_circular_dependency ? '#ef4444' : '#10b981' }}>
                  {lineageReport.execution_order?.has_circular_dependency ? 'Yes' : 'No'}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Main Area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {/* Top Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 16px',
          borderBottom: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`,
          backgroundColor: theme === 'dark' ? '#111827' : '#ffffff',
          position: 'sticky',
          top: 0,
          zIndex: 1000
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', color: theme === 'dark' ? 'white' : '#111827', fontWeight: 600 }}>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={() => { setShowTablesSection(true); setShowProceduresSection(false); setShowTableDetailsSection(false); }}
                style={{
                  padding: '8px 12px',
                  backgroundColor: showTablesSection ? (theme === 'dark' ? '#2563eb' : '#3b82f6') : (theme === 'dark' ? '#1f2937' : '#ffffff'),
                  color: showTablesSection ? 'white' : (theme === 'dark' ? '#e5e7eb' : '#111827'),
                  border: '1px solid ' + (showTablesSection ? (theme === 'dark' ? '#1d4ed8' : '#60a5fa') : (theme === 'dark' ? '#374151' : '#e5e7eb')),
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontSize: '13px',
                  fontWeight: 600
                }}
              >
                Tabular Components
              </button>
              <button
                onClick={() => { setShowTablesSection(false); setShowProceduresSection(true); setShowTableDetailsSection(false); }}
                style={{
                  padding: '8px 12px',
                  backgroundColor: showProceduresSection ? (theme === 'dark' ? '#2563eb' : '#3b82f6') : (theme === 'dark' ? '#1f2937' : '#ffffff'),
                  color: showProceduresSection ? 'white' : (theme === 'dark' ? '#e5e7eb' : '#111827'),
                  border: '1px solid ' + (showProceduresSection ? (theme === 'dark' ? '#1d4ed8' : '#60a5fa') : (theme === 'dark' ? '#374151' : '#e5e7eb')),
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontSize: '13px',
                  fontWeight: 600
                }}
              >
                Executable Components
              </button>
              <button
                onClick={() => { setShowTablesSection(false); setShowProceduresSection(false); setShowTableDetailsSection(true); }}
                style={{
                  padding: '8px 12px',
                  backgroundColor: showTableDetailsSection ? (theme === 'dark' ? '#2563eb' : '#3b82f6') : (theme === 'dark' ? '#1f2937' : '#ffffff'),
                  color: showTableDetailsSection ? 'white' : (theme === 'dark' ? '#e5e7eb' : '#111827'),
                  border: '1px solid ' + (showTableDetailsSection ? (theme === 'dark' ? '#1d4ed8' : '#60a5fa') : (theme === 'dark' ? '#374151' : '#e5e7eb')),
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontSize: '13px',
                  fontWeight: 600
                }}
              >
                Tabular Component List
              </button>
              {/* Functions tab removed; functions and UDFs are shown under Procedures */}
            </div>
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => setTheme(prev => prev === 'dark' ? 'light' : 'dark')}
              title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
              style={{
                padding: '8px',
                backgroundColor: theme === 'dark' ? '#374151' : '#e5e7eb',
                color: theme === 'dark' ? 'white' : '#111827',
                border: '1px solid ' + (theme === 'dark' ? '#4b5563' : '#d1d5db'),
                borderRadius: '6px',
                cursor: 'pointer',
                boxShadow: '0 2px 6px rgba(0,0,0,0.2)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
            >
              {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <button
              onClick={() => {
                setShowAllColumnConnections(prev => !prev);
                if (!showAllColumnConnections && lineageData) {
                  const participating = new Set();
                  lineageData.connections.forEach(c => {
                    participating.add(c.sourceTable);
                    participating.add(c.targetTable);
                  });
                  const toExpand = Array.from(participating).filter(tn => !expandedTables.has(tn));
                  if (toExpand.length > 0) {
                    ensureTablesExpanded(toExpand);
                    setAutoExpandedOnShowAll(new Set(toExpand));
                  }
                } else if (showAllColumnConnections) {
                  if (autoExpandedOnShowAll.size > 0) {
                    ensureTablesCollapsed(Array.from(autoExpandedOnShowAll));
                    setAutoExpandedOnShowAll(new Set());
                  }
                }
              }}
              title={showAllColumnConnections ? 'Hide all column connections' : 'Show all column connections'}
              style={{
                padding: '8px',
                backgroundColor: theme === 'dark' ? '#2563eb' : '#3b82f6',
                color: 'white',
                border: '1px solid ' + (theme === 'dark' ? '#1d4ed8' : '#60a5fa'),
                borderRadius: '6px',
                cursor: 'pointer',
                boxShadow: '0 2px 6px rgba(0,0,0,0.2)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
            >
              <Link2 size={16} />
            </button>
            <button
              onClick={handlePreviewSVG}
              disabled={showProceduresSection ? (!procedureLineageData || !selectedProcedure) : !lineageData}
              style={{
                padding: '8px',
                backgroundColor: (showProceduresSection ? (!procedureLineageData || !selectedProcedure) : !lineageData) ? '#9ca3af' : (theme === 'dark' ? '#4f46e5' : '#6366f1'),
                color: 'white',
                border: '1px solid ' + (theme === 'dark' ? '#4338ca' : '#a5b4fc'),
                borderRadius: '6px',
                cursor: (showProceduresSection ? (!procedureLineageData || !selectedProcedure) : !lineageData) ? 'not-allowed' : 'pointer',
                opacity: (showProceduresSection ? (!procedureLineageData || !selectedProcedure) : !lineageData) ? 0.6 : 1,
                boxShadow: '0 2px 6px rgba(0,0,0,0.2)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
              title={(showProceduresSection ? (!procedureLineageData || !selectedProcedure) : !lineageData) 
                ? 'Load data first' 
                : 'Preview SVG before download'}
            >
              <Eye size={16} />
            </button>
            <button
              onClick={handleExportSVG}
              disabled={showProceduresSection ? (!procedureLineageData || !selectedProcedure) : !lineageData}
              style={{
                padding: '8px',
                backgroundColor: (showProceduresSection ? (!procedureLineageData || !selectedProcedure) : !lineageData) ? '#9ca3af' : (theme === 'dark' ? '#059669' : '#10b981'),
                color: 'white',
                border: '1px solid ' + (theme === 'dark' ? '#065f46' : '#34d399'),
                borderRadius: '6px',
                cursor: (showProceduresSection ? (!procedureLineageData || !selectedProcedure) : !lineageData) ? 'not-allowed' : 'pointer',
                opacity: (showProceduresSection ? (!procedureLineageData || !selectedProcedure) : !lineageData) ? 0.6 : 1,
                boxShadow: '0 2px 6px rgba(0,0,0,0.2)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
              title={(showProceduresSection ? (!procedureLineageData || !selectedProcedure) : !lineageData) 
                ? 'Load data first' 
                : 'Export current view as SVG'}
            >
              <Download size={16} />
            </button>
          </div>
        </div>

        {/* Main Content Area - Canvas and Right Panel */}
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden', position: 'relative', minHeight: 0 }}>
          {/* Canvas Area */}
          <div
            ref={canvasRef}
            className="canvas-container"
            style={{
              flex: '1 1 auto',
              flexBasis: shouldReserveRightPanelSpace ? `calc(100% - ${RIGHT_PANEL_WIDTH}px)` : '100%',
              overflow: 'hidden',
              position: 'relative',
              backgroundColor: theme === 'dark' ? '#0b0f14' : '#f7f7f5',
              cursor: isDragging ? 'grabbing' : 'grab',
              backgroundImage: theme === 'dark'
                ? 'radial-gradient(circle, #2b3440 1px, transparent 1px)'
                : 'radial-gradient(circle, #d8d8d4 1px, transparent 1px)',
              backgroundSize: '20px 20px',
              transition: 'flex-basis 0.35s ease',
              minHeight: 0,
              minWidth: 0
            }}
            onMouseDown={handleMouseDown}
          >
          <div style={{ width: '100%', height: '100%', overflow: 'auto' }}>
          {showProceduresSection ? renderProcedureLineage() : lineageData ? (
            showTableDetailsSection ? renderTableDetails() : renderLineage()
          ) : (
            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center', 
              height: '100%' 
            }}>
              <div style={{ textAlign: 'center' }}>
                <Database size={64} style={{ margin: '0 auto', color: '#4b5563', marginBottom: '16px' }} />
                <p style={{ color: '#9ca3af', fontSize: '18px', fontWeight: 500 }}>No lineage data</p>
                <p style={{ color: '#6b7280', fontSize: '14px', marginTop: '8px' }}>Click "Load Lineage Report" to load data</p>
              </div>
            </div>
          )}

           {/* Zoom Controls - Bottom Right (positioned relative to canvas, behind panel) */}
           <div style={{
             position: 'absolute',
             bottom: '20px',
             right: '20px',
             display: 'flex',
             flexDirection: 'column',
             gap: '8px',
             backgroundColor: 'rgba(31, 41, 55, 0.9)',
             padding: '12px',
             borderRadius: '8px',
             border: '1px solid #374151',
             backdropFilter: 'blur(10px)',
             boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
             zIndex: 1000,
             transition: 'right 0.3s ease'
           }}>
            <button
              onClick={() => handleZoom('in')}
              style={{
                padding: '8px',
                backgroundColor: '#374151',
                border: 'none',
                borderRadius: '6px',
                color: 'white',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'background-color 0.35s'
              }}
            >
              <ZoomIn size={16} />
            </button>
            <span style={{ 
              padding: '4px 8px', 
              backgroundColor: '#374151', 
              borderRadius: '6px', 
              fontSize: '11px', 
              fontFamily: 'monospace',
              textAlign: 'center',
              color: 'white'
            }}>
              {Math.round(zoom * 100)}%
            </span>
            <button
              onClick={() => handleZoom('out')}
              style={{
                padding: '8px',
                backgroundColor: '#374151',
                border: 'none',
                borderRadius: '6px',
                color: 'white',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              transition: 'background-color 0.35s'
              }}
            >
              <ZoomOut size={16} />
            </button>
            <button
              onClick={handleReset}
              style={{
                padding: '8px',
                backgroundColor: '#374151',
                border: 'none',
                borderRadius: '6px',
                color: 'white',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'background-color 0.2s'
              }}
            >
              <Maximize2 size={16} />
            </button>
          </div>
          </div>

          {/* Reopen Panel Button - Show when panel is closed */}
          {isProcedurePanelActive && !isRightPanelOpen && (
            <button
              onClick={() => setIsRightPanelOpen(true)}
              style={{
                position: 'absolute',
                right: '0',
                top: '50%',
                transform: 'translateY(-50%)',
                zIndex: 1001,
                padding: '12px 8px',
                backgroundColor: theme === 'dark' ? '#1f2937' : '#ffffff',
                border: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`,
                borderRight: 'none',
                borderRadius: '8px 0 0 8px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
                color: theme === 'dark' ? '#e5e7eb' : '#111827',
                transition: 'all 0.2s ease'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = theme === 'dark' ? '#374151' : '#f3f4f6';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = theme === 'dark' ? '#1f2937' : '#ffffff';
              }}
              title="Reopen procedure details panel"
            >
              <ChevronLeft size={20} />
            </button>
          )}

            </div>

          {/* Right Panel - Procedure Details */}
          {isProcedurePanelActive && (() => {
            const procData = procedureLineage?.procedures?.[selectedProcedure] 
              || procedureLineage?.functions?.[selectedProcedure]
              || procedureLineage?.triggers?.[selectedProcedure];
            if (!procData) return null;

            const originalSQL = procData.modified_sql || procData.original_sql || '';
            const llmResponse = procData.llm_raw_response || procData.lineage_analysis || '';

            return (
              <div style={{
                width: isRightPanelOpen ? `${RIGHT_PANEL_WIDTH}px` : '0px',
                borderLeft: isRightPanelOpen ? `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}` : 'none',
                backgroundColor: theme === 'dark' ? '#1f2937' : '#ffffff',
                display: 'flex',
                flexDirection: 'column',
                overflow: 'hidden',
                position: 'relative',
                height: '100%',
                boxShadow: isRightPanelOpen ? '0 10px 30px rgba(15, 23, 42, 0.35)' : 'none',
                transition: 'width 0.35s ease, box-shadow 0.35s ease',
                willChange: 'width'
              }}>
                <div style={{
                  opacity: isRightPanelOpen ? 1 : 0,
                  transform: isRightPanelOpen ? 'translateX(0)' : 'translateX(16px)',
                  transition: 'opacity 0.3s ease, transform 0.3s ease',
                  pointerEvents: isRightPanelOpen ? 'auto' : 'none',
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column'
                }}>
                  {/* Panel Header */}
                  <div style={{
                    padding: '16px',
                    borderBottom: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between'
                  }}>
                    <h3 style={{
                      margin: 0,
                      fontSize: '16px',
                      fontWeight: 700,
                      color: theme === 'dark' ? 'white' : '#111827'
                    }}>
                      {selectedProcedure}
                    </h3>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      <button
                        onClick={() => setIsRightPanelOpen(false)}
                        style={{
                          background: 'transparent',
                          border: 'none',
                          cursor: 'pointer',
                          color: theme === 'dark' ? '#9ca3af' : '#6b7280',
                          padding: '4px',
                          display: 'flex',
                          alignItems: 'center',
                          transition: 'color 0.2s ease'
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.color = theme === 'dark' ? '#e5e7eb' : '#111827';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.color = theme === 'dark' ? '#9ca3af' : '#6b7280';
                        }}
                        title="Collapse panel"
                      >
                        <ChevronRight size={20} />
                      </button>
                    </div>
                  </div>

                  {/* Panel Content */}
                  <div style={{
                    flex: 1,
                    overflow: 'auto',
                    display: 'flex',
                    flexDirection: 'column'
                  }}>
                    {/* Original SQL Section */}
                    <div style={{
                      padding: '16px',
                      borderBottom: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`
                    }}>
                      <h4 style={{
                        margin: '0 0 12px 0',
                        fontSize: '14px',
                        fontWeight: 600,
                        color: theme === 'dark' ? 'white' : '#111827',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px'
                      }}>
                        <File size={16} />
                        Original SQL
                      </h4>
                      <div style={{
                        background: theme === 'dark' ? '#0b0f14' : '#f3f4f6',
                        borderRadius: '8px',
                        padding: '12px',
                        border: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`,
                        maxHeight: '300px',
                        overflow: 'auto',
                        fontFamily: 'monospace',
                        fontSize: '12px',
                        lineHeight: '1.6',
                        color: theme === 'dark' ? '#e5e7eb' : '#111827',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word'
                      }}>
                        {originalSQL || 'No SQL code available'}
                      </div>
                    </div>

                    {/* LLM Response Section */}
                    <div style={{
                      padding: '16px',
                      flex: 1,
                      display: 'flex',
                      flexDirection: 'column',
                      minHeight: 0
                    }}>
                      <h4 style={{
                        margin: '0 0 12px 0',
                        fontSize: '14px',
                        fontWeight: 600,
                        color: theme === 'dark' ? 'white' : '#111827',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px'
                      }}>
                        <Database size={16} />
                        LLM Response
                      </h4>
                      <div style={{
                        background: theme === 'dark' ? '#0b0f14' : '#f3f4f6',
                        borderRadius: '8px',
                        padding: '12px',
                        border: `1px solid ${theme === 'dark' ? '#374151' : '#e5e7eb'}`,
                        flex: 1,
                        overflow: 'auto',
                        fontFamily: 'monospace',
                        fontSize: '12px',
                        lineHeight: '1.6',
                        color: theme === 'dark' ? '#e5e7eb' : '#111827',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                        minHeight: 0
                      }}>
                        {llmResponse ? (
                          <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                            {typeof llmResponse === 'string' 
                              ? llmResponse 
                              : JSON.stringify(llmResponse, null, 2)}
                          </pre>
                        ) : 'No LLM response available'}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            );
          })()}
        </div>
        
        {/* Top-right controls moved into header above */}
        {/* Preview Modal */}
        <SVGPreviewModal
          open={isPreviewOpen}
          svg={previewSVG}
          onClose={() => setIsPreviewOpen(false)}
          onDownload={handleExportSVG}
        />
      </div>
    </div>
    </>
  );
};

export default SQLLineageViz;
 
// Simple inline preview modal
const SVGPreviewModal = ({ open, svg, onClose, onDownload }) => {
  if (!open) return null;
  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 2000
    }}>
      <div style={{ background: '#111827', color: 'white', padding: '16px', borderRadius: '8px', maxWidth: '90vw', maxHeight: '80vh', display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontWeight: 600 }}>SVG Preview</div>
          <button onClick={onClose} style={{ background: '#374151', color: 'white', border: '1px solid #4b5563', borderRadius: '6px', padding: '6px 10px', cursor: 'pointer' }}>Close</button>
        </div>
        <div style={{ background: 'white', padding: '8px', borderRadius: '6px', overflow: 'auto' }}>
          <div dangerouslySetInnerHTML={{ __html: svg }} />
        </div>
        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
          <button onClick={onDownload} style={{ background: '#059669', color: 'white', border: '1px solid #065f46', borderRadius: '6px', padding: '8px 12px', cursor: 'pointer' }}>Download</button>
        </div>
      </div>
    </div>
  );
};