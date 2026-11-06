/** Runs SQL statements sent by the Python app against the D1 binding. */
export type Statement = { sql: string; params?: unknown[] };
export const READ = /^\s*(select|pragma|with|explain)\b/i;

export async function runStatements(db: D1Database, statements: Statement[]) {
  const prepared = statements.map((s) => db.prepare(s.sql).bind(...(s.params ?? [])));
  // Several writes (e.g. executemany): one atomic batch.
  if (statements.length > 1 && statements.every((s) => !READ.test(s.sql))) {
    const rs = await db.batch(prepared);
    return rs.map((r) => ({ columns: [], rows: [], last_row_id: r.meta.last_row_id, changes: r.meta.changes }));
  }
  const out = [];
  for (let i = 0; i < statements.length; i++) {
    if (READ.test(statements[i].sql)) {
      const raw = (await prepared[i].raw({ columnNames: true })) as unknown[][];
      const [columns = [], ...rows] = raw;
      out.push({ columns, rows });
    } else {
      const r = await prepared[i].run();
      out.push({ columns: [], rows: [], last_row_id: r.meta.last_row_id, changes: r.meta.changes });
    }
  }
  return out;
}
