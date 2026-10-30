export interface EditableColumnDef<T extends object> {
  key: keyof T & string;
  header: string;
  type?: 'text' | 'number' | 'select' | 'textarea';
  options?: Array<{ value: string; label: string }>;
  placeholder?: string;
  minWidth?: string;
  readOnly?: boolean;
}

interface EditableTableProps<T extends object> {
  columns: EditableColumnDef<T>[];
  rows: T[];
  onChange: (rows: T[]) => void;
  emptyMessage?: string;
  newRow: () => T;
  rowKey?: (row: T, index: number) => string;
}

const cellInputClass =
  'w-full min-w-0 px-2 py-1 border border-brand-border rounded text-xs bg-white text-brand-ink font-sans';

function cellValue<T extends object>(row: T, key: keyof T & string): string {
  return String((row as Record<string, unknown>)[key] ?? '');
}

export function EditableTable<T extends object>({
  columns,
  rows,
  onChange,
  emptyMessage = 'No rows yet.',
  newRow,
  rowKey,
}: EditableTableProps<T>) {
  const updateRow = (index: number, key: keyof T & string, value: unknown) => {
    const next = rows.map((row, i) => (i === index ? ({ ...row, [key]: value } as T) : row));
    onChange(next);
  };

  const removeRow = (index: number) => {
    onChange(rows.filter((_, i) => i !== index));
  };

  const addRow = () => {
    onChange([...rows, newRow()]);
  };

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto border border-brand-border rounded-lg">
        <table className="min-w-full text-xs">
          <thead className="bg-brand-surface-muted sticky top-0">
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  className="text-left p-2 font-medium text-brand-ink whitespace-nowrap"
                  style={col.minWidth ? { minWidth: col.minWidth } : undefined}
                >
                  {col.header}
                </th>
              ))}
              <th className="p-2 w-10" aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length + 1} className="p-4 text-brand-muted text-center">
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              rows.map((row, index) => (
                <tr key={rowKey ? rowKey(row, index) : index} className="border-t border-brand-border align-top">
                  {columns.map((col) => (
                    <td key={col.key} className="p-2">
                      {col.readOnly ? (
                        <span className="text-brand-muted">{cellValue(row, col.key)}</span>
                      ) : col.type === 'select' && col.options ? (
                        <select
                          className={cellInputClass}
                          value={cellValue(row, col.key)}
                          onChange={(e) => updateRow(index, col.key, e.target.value)}
                        >
                          <option value="">—</option>
                          {col.options.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      ) : col.type === 'textarea' ? (
                        <textarea
                          className={`${cellInputClass} min-h-[3rem] resize-y`}
                          value={cellValue(row, col.key)}
                          placeholder={col.placeholder}
                          onChange={(e) => updateRow(index, col.key, e.target.value)}
                        />
                      ) : col.type === 'number' ? (
                        <input
                          type="number"
                          className={cellInputClass}
                          value={cellValue(row, col.key)}
                          placeholder={col.placeholder}
                          onChange={(e) =>
                            updateRow(
                              index,
                              col.key,
                              e.target.value === '' ? undefined : Number(e.target.value),
                            )
                          }
                        />
                      ) : (
                        <input
                          type="text"
                          className={cellInputClass}
                          value={cellValue(row, col.key)}
                          placeholder={col.placeholder}
                          onChange={(e) => updateRow(index, col.key, e.target.value)}
                        />
                      )}
                    </td>
                  ))}
                  <td className="p-2">
                    <button
                      type="button"
                      onClick={() => removeRow(index)}
                      className="text-brand-muted hover:text-red-600 text-sm"
                      title="Remove row"
                    >
                      ×
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <button
        type="button"
        onClick={addRow}
        className="text-xs px-2.5 py-1 rounded border border-brand-border text-brand-muted hover:bg-brand-surface-muted"
      >
        + Add row
      </button>
    </div>
  );
}
