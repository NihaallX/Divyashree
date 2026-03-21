"""
Neon/PostgreSQL database client.
Provides a compatibility-style table query compatibility layer for existing routes.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from loguru import logger
import psycopg2
from psycopg2 import pool
from psycopg2.extras import Json, RealDictCursor


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class QueryResult:
    data: List[Dict[str, Any]]
    count: Optional[int] = None


class _NegationProxy:
    def __init__(self, query: "TableQuery") -> None:
        self._query = query

    def is_(self, column: str, value: Any) -> "TableQuery":
        return self._query._is_clause(column, value, negate=True)


class TableQuery:
    def __init__(self, db: "RelayDB", table_name: str) -> None:
        self._db = db
        self._table = self._validate_identifier(table_name)
        self._operation = "select"
        self._select_clause = "*"
        self._count_mode: Optional[str] = None
        self._payload: Any = None
        self._conditions: List[Tuple[str, List[Any]]] = []
        self._order_by: Optional[str] = None
        self._limit: Optional[int] = None

    @property
    def not_(self) -> _NegationProxy:
        return _NegationProxy(self)

    def select(self, columns: str, count: Optional[str] = None) -> "TableQuery":
        self._operation = "select"
        self._select_clause = columns or "*"
        self._count_mode = count
        return self

    def insert(self, payload: Any) -> "TableQuery":
        self._operation = "insert"
        self._payload = payload
        return self

    def update(self, payload: Dict[str, Any]) -> "TableQuery":
        self._operation = "update"
        self._payload = payload
        return self

    def delete(self) -> "TableQuery":
        self._operation = "delete"
        return self

    def upsert(self, payload: Any) -> "TableQuery":
        self._operation = "upsert"
        self._payload = payload
        return self

    def eq(self, column: str, value: Any) -> "TableQuery":
        return self._where(column, "=", value)

    def gte(self, column: str, value: Any) -> "TableQuery":
        return self._where(column, ">=", value)

    def lte(self, column: str, value: Any) -> "TableQuery":
        return self._where(column, "<=", value)

    def gt(self, column: str, value: Any) -> "TableQuery":
        return self._where(column, ">", value)

    def lt(self, column: str, value: Any) -> "TableQuery":
        return self._where(column, "<", value)

    def ilike(self, column: str, value: str) -> "TableQuery":
        return self._where(column, "ILIKE", value)

    def in_(self, column: str, values: Sequence[Any]) -> "TableQuery":
        column = self._validate_identifier(column)
        if not values:
            self._conditions.append(("1 = 0", []))
            return self
        placeholders = ", ".join(["%s"] * len(values))
        self._conditions.append((f"{column} IN ({placeholders})", list(values)))
        return self

    def is_(self, column: str, value: Any) -> "TableQuery":
        return self._is_clause(column, value, negate=False)

    def order(self, column: str, desc: bool = False) -> "TableQuery":
        column = self._validate_identifier(column)
        direction = "DESC" if desc else "ASC"
        self._order_by = f"{column} {direction}"
        return self

    def limit(self, count: int) -> "TableQuery":
        self._limit = max(0, int(count))
        return self

    def execute(self) -> QueryResult:
        if self._operation == "select":
            return self._run_select()
        if self._operation == "insert":
            return self._run_insert()
        if self._operation == "update":
            return self._run_update()
        if self._operation == "delete":
            return self._run_delete()
        if self._operation == "upsert":
            return self._run_upsert()
        raise ValueError(f"Unsupported operation: {self._operation}")

    def _run_select(self) -> QueryResult:
        join_spec = self._parse_join_select(self._select_clause)
        select_sql = "*"
        from_sql = f"{self._table} t"

        if join_spec:
            alias_key, join_table, join_cols, fk_col = join_spec
            join_table = self._validate_identifier(join_table)
            fk_col = self._validate_identifier(fk_col)
            select_parts = ["t.*"]
            for col in join_cols:
                col = self._validate_identifier(col)
                select_parts.append(f"j.{col} AS __{alias_key}_{col}")
            select_sql = ", ".join(select_parts)
            from_sql += f" LEFT JOIN {join_table} j ON t.{fk_col} = j.id"
        else:
            select_sql = self._to_select_sql(self._select_clause)

        where_sql, params = self._compile_conditions(prefix="t")
        sql = f"SELECT {select_sql} FROM {from_sql}"
        if where_sql:
            sql += f" WHERE {where_sql}"
        if self._order_by:
            sql += f" ORDER BY t.{self._order_by}"
        if self._limit is not None:
            sql += " LIMIT %s"
            params.append(self._limit)

        rows = self._db._fetch_all(sql, params)
        if join_spec:
            alias_key, _, join_cols, _ = join_spec
            rows = self._nest_join_columns(rows, alias_key, join_cols)

        count_value = None
        if self._count_mode == "exact":
            count_sql = f"SELECT COUNT(*)::int AS c FROM {self._table} t"
            count_where, count_params = self._compile_conditions(prefix="t")
            if count_where:
                count_sql += f" WHERE {count_where}"
            count_row = self._db._fetch_one(count_sql, count_params)
            count_value = count_row["c"] if count_row else 0

        return QueryResult(data=rows, count=count_value)

    def _run_insert(self) -> QueryResult:
        rows = self._payload if isinstance(self._payload, list) else [self._payload]
        if not rows:
            return QueryResult(data=[])

        cleaned_rows: List[Dict[str, Any]] = []
        for row in rows:
            cleaned_rows.append({k: v for k, v in row.items() if v is not None})

        cols = list(cleaned_rows[0].keys())
        self._validate_columns(cols)

        values_sql = []
        params: List[Any] = []
        for row in cleaned_rows:
            row_params = [self._db._adapt_value(row.get(col)) for col in cols]
            params.extend(row_params)
            values_sql.append("(" + ", ".join(["%s"] * len(cols)) + ")")

        col_sql = ", ".join(cols)
        sql = (
            f"INSERT INTO {self._table} ({col_sql}) VALUES {', '.join(values_sql)} "
            "RETURNING *"
        )
        return QueryResult(data=self._db._fetch_all(sql, params))

    def _run_update(self) -> QueryResult:
        if not self._payload:
            return QueryResult(data=[])

        updates = {k: v for k, v in self._payload.items()}
        cols = list(updates.keys())
        self._validate_columns(cols)

        set_sql = ", ".join([f"{c} = %s" for c in cols])
        params = [self._db._adapt_value(updates[c]) for c in cols]

        where_sql, where_params = self._compile_conditions(prefix=None)
        params.extend(where_params)

        sql = f"UPDATE {self._table} SET {set_sql}"
        if where_sql:
            sql += f" WHERE {where_sql}"
        sql += " RETURNING *"
        return QueryResult(data=self._db._fetch_all(sql, params))

    def _run_delete(self) -> QueryResult:
        where_sql, params = self._compile_conditions(prefix=None)
        sql = f"DELETE FROM {self._table}"
        if where_sql:
            sql += f" WHERE {where_sql}"
        sql += " RETURNING *"
        return QueryResult(data=self._db._fetch_all(sql, params))

    def _run_upsert(self) -> QueryResult:
        rows = self._payload if isinstance(self._payload, list) else [self._payload]
        if not rows:
            return QueryResult(data=[])

        data = {k: v for k, v in rows[0].items() if v is not None}
        cols = list(data.keys())
        self._validate_columns(cols)

        conflict_col = self._conflict_column()
        col_sql = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))
        params = [self._db._adapt_value(data[c]) for c in cols]

        if conflict_col and conflict_col in cols:
            update_cols = [c for c in cols if c != conflict_col]
            if update_cols:
                update_sql = ", ".join([f"{c} = EXCLUDED.{c}" for c in update_cols])
            else:
                update_sql = f"{conflict_col} = EXCLUDED.{conflict_col}"
            sql = (
                f"INSERT INTO {self._table} ({col_sql}) VALUES ({placeholders}) "
                f"ON CONFLICT ({conflict_col}) DO UPDATE SET {update_sql} RETURNING *"
            )
            return QueryResult(data=self._db._fetch_all(sql, params))

        return self._run_insert()

    def _compile_conditions(self, prefix: Optional[str]) -> Tuple[str, List[Any]]:
        if not self._conditions:
            return "", []

        clauses: List[str] = []
        params: List[Any] = []
        for sql_clause, clause_params in self._conditions:
            if prefix and re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s", sql_clause):
                col, rest = sql_clause.split(" ", 1)
                sql_clause = f"{prefix}.{col} {rest}"
            clauses.append(sql_clause)
            params.extend([self._db._adapt_value(x) for x in clause_params])

        return " AND ".join(clauses), params

    def _where(self, column: str, operator: str, value: Any) -> "TableQuery":
        column = self._validate_identifier(column)
        self._conditions.append((f"{column} {operator} %s", [value]))
        return self

    def _is_clause(self, column: str, value: Any, negate: bool) -> "TableQuery":
        column = self._validate_identifier(column)
        is_null = value is None or (isinstance(value, str) and value.lower() == "null")
        if is_null:
            self._conditions.append((f"{column} IS {'NOT ' if negate else ''}NULL", []))
        else:
            operator = "<>" if negate else "="
            self._conditions.append((f"{column} {operator} %s", [value]))
        return self

    def _to_select_sql(self, clause: str) -> str:
        if clause.strip() == "*":
            return "t.*"

        if "(" in clause or ")" in clause or ":" in clause:
            logger.warning(f"Unsupported relational select '{clause}', falling back to t.*")
            return "t.*"

        columns = [self._validate_identifier(c.strip()) for c in clause.split(",") if c.strip()]
        if not columns:
            return "t.*"
        return ", ".join([f"t.{c}" for c in columns])

    def _parse_join_select(self, clause: str) -> Optional[Tuple[str, str, List[str], str]]:
        text = clause.replace(" ", "")
        aliased = re.fullmatch(r"\*,([A-Za-z_][A-Za-z0-9_]*):([A-Za-z_][A-Za-z0-9_]*)\(([A-Za-z0-9_,]+)\)", text)
        if aliased:
            alias, join_table, cols = aliased.groups()
            col_list = [c for c in cols.split(",") if c]
            fk_col = "agent_id" if join_table == "agent" else f"{join_table}_id"
            if join_table == "agent":
                join_table = "agents"
            return alias, join_table, col_list, fk_col

        simple = re.fullmatch(r"\*,([A-Za-z_][A-Za-z0-9_]*)\(([A-Za-z0-9_,]+)\)", text)
        if simple:
            join_table, cols = simple.groups()
            col_list = [c for c in cols.split(",") if c]
            fk_col = "agent_id" if join_table in {"agent", "agents"} else f"{join_table}_id"
            if join_table == "agent":
                join_table = "agents"
            return join_table, join_table, col_list, fk_col

        return None

    def _nest_join_columns(
        self, rows: List[Dict[str, Any]], alias_key: str, join_cols: List[str]
    ) -> List[Dict[str, Any]]:
        nested_rows: List[Dict[str, Any]] = []
        for row in rows:
            nested: Dict[str, Any] = {}
            has_join_data = False
            for col in join_cols:
                key = f"__{alias_key}_{col}"
                val = row.pop(key, None)
                if val is not None:
                    has_join_data = True
                nested[col] = val
            row[alias_key] = nested if has_join_data else None
            nested_rows.append(row)
        return nested_rows

    def _validate_columns(self, columns: List[str]) -> None:
        for col in columns:
            self._validate_identifier(col)

    def _conflict_column(self) -> Optional[str]:
        return {
            "call_analysis": "call_id",
            "users": "email",
            "auth_tokens": "refresh_token",
        }.get(self._table)

    @staticmethod
    def _validate_identifier(name: str) -> str:
        if not _IDENTIFIER.match(name):
            raise ValueError(f"Invalid SQL identifier: {name}")
        return name


class CompatClient:
    def __init__(self, db: "RelayDB") -> None:
        self._db = db

    def table(self, table_name: str) -> TableQuery:
        return TableQuery(self._db, table_name)


class RelayDB:
    """Database wrapper preserving legacy API while using PostgreSQL directly."""

    def __init__(
        self,
        database_url: Optional[str] = None,
        url: Optional[str] = None,
        key: Optional[str] = None,
    ):
        # `url` and `key` are kept only for backward compatibility with old call sites.
        _ = (url, key)
        self.database_url = database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise ValueError("DATABASE_URL must be set for Neon/PostgreSQL")

        self._pool = pool.SimpleConnectionPool(
            minconn=1,
            maxconn=int(os.getenv("DB_POOL_SIZE", "10")),
            dsn=self.database_url,
        )
        self.client = CompatClient(self)
        logger.info("PostgreSQL client initialized via DATABASE_URL")

    # ==================== Internal Helpers ====================

    def _get_conn(self):
        return self._pool.getconn()

    def _put_conn(self, conn) -> None:
        self._pool.putconn(conn)

    def _adapt_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            return Json(value)
        if isinstance(value, datetime):
            return value
        return value

    def _normalize_value(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, list):
            return [self._normalize_value(v) for v in value]
        if isinstance(value, dict):
            return {k: self._normalize_value(v) for k, v in value.items()}
        return value

    def _normalize_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [{k: self._normalize_value(v) for k, v in row.items()} for row in rows]

    def _fetch_all(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params or [])
                rows = cur.fetchall() if cur.description else []
            conn.commit()
            return self._normalize_rows(rows)
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put_conn(conn)

    def _fetch_one(self, sql: str, params: Optional[List[Any]] = None) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params or [])
                row = cur.fetchone() if cur.description else None
            conn.commit()
            if row is None:
                return None
            return {k: self._normalize_value(v) for k, v in row.items()}
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put_conn(conn)

    # ==================== AGENTS ====================

    async def create_agent(self, name: str, prompt_text: str, template_source: str = None, **kwargs) -> Dict[str, Any]:
        data = {
            "name": name,
            "prompt_text": prompt_text,
            "template_source": template_source,
            **kwargs,
        }
        result = self.client.table("agents").insert(data).execute()
        logger.info(f"Created agent: {name}")
        return result.data[0]

    async def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        result = self.client.table("agents").select("*").eq("id", agent_id).execute()
        if not result.data:
            return None
        agent = result.data[0]
        agent["resolved_system_prompt"] = agent.get("prompt_text") or "You are a helpful AI assistant."
        return agent

    async def list_agents(self, is_active: bool = True) -> List[Dict[str, Any]]:
        query = self.client.table("agents").select("*")
        if is_active is not None:
            query = query.eq("is_active", is_active)
        return query.execute().data

    async def update_agent(self, agent_id: str, **kwargs) -> Dict[str, Any]:
        result = self.client.table("agents").update(kwargs).eq("id", agent_id).execute()
        logger.info(f"Updated agent {agent_id}")
        return result.data[0]

    # ==================== CALLS ====================

    async def create_call(self, agent_id: str, to_number: str, from_number: str, **kwargs) -> Dict[str, Any]:
        data = {
            "agent_id": agent_id,
            "to_number": to_number,
            "from_number": from_number,
            "status": "initiated",
            **kwargs,
        }
        result = self.client.table("calls").insert(data).execute()
        logger.info(f"Created call record: {result.data[0]['id']}")
        return result.data[0]

    async def get_call(self, call_id: str) -> Optional[Dict[str, Any]]:
        result = self.client.table("calls").select("*").eq("id", call_id).execute()
        if not result.data:
            return None
        call_data = result.data[0]
        if call_data.get("agent_id"):
            agent = self.client.table("agents").select("*").eq("id", call_data["agent_id"]).execute().data
            call_data["agents"] = agent[0] if agent else None
        return call_data

    async def update_call(self, call_id: str, **kwargs) -> Dict[str, Any]:
        for key, value in kwargs.items():
            if isinstance(value, datetime):
                kwargs[key] = value.isoformat()
        result = self.client.table("calls").update(kwargs).eq("id", call_id).execute()
        logger.info(f"Updated call {call_id}: {list(kwargs.keys())}")
        return result.data[0]

    async def update_call_by_sid(self, twilio_call_sid: str, **kwargs) -> Optional[Dict[str, Any]]:
        result = self.client.table("calls").update(kwargs).eq("twilio_call_sid", twilio_call_sid).execute()
        return result.data[0] if result.data else None

    async def list_calls(
        self, agent_id: Optional[str] = None, status: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        query = self.client.table("calls").select("*, agents(name)")
        if agent_id:
            query = query.eq("agent_id", agent_id)
        if status:
            query = query.eq("status", status)
        query = query.order("created_at", desc=True).limit(limit)
        calls = query.execute().data

        normalized = []
        for call in calls:
            row = call.copy()
            if row.get("agents"):
                row["agent_name"] = row["agents"].get("name")
            normalized.append(row)
        return normalized

    # ==================== TRANSCRIPTS ====================

    async def save_transcript(
        self,
        call_id: str,
        speaker: str,
        text: str,
        audio_duration: Optional[float] = None,
        confidence_score: Optional[float] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        data = {
            "call_id": call_id,
            "speaker": speaker,
            "text": text,
            "audio_duration": audio_duration,
            "confidence_score": confidence_score,
            "metadata": metadata or {},
        }
        result = self.client.table("transcripts").insert(data).execute()
        return result.data[0]

    async def add_transcript(self, call_id: str, speaker: str, text: str, **kwargs) -> Dict[str, Any]:
        data = {"call_id": call_id, "speaker": speaker, "text": text, **kwargs}
        result = self.client.table("transcripts").insert(data).execute()
        return result.data[0]

    async def get_transcripts(self, call_id: str) -> List[Dict[str, Any]]:
        result = self.client.table("transcripts").select("*").eq("call_id", call_id).order("timestamp").execute()
        return result.data

    async def get_conversation_history(self, call_id: str, limit: int = 10) -> List[Dict[str, str]]:
        result = (
            self.client.table("transcripts")
            .select("speaker, text")
            .eq("call_id", call_id)
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
        )

        history = []
        for item in reversed(result.data):
            role = "assistant" if item["speaker"] == "agent" else "user"
            history.append({"role": role, "content": item["text"]})
        return history

    # ==================== TEMPLATES ====================

    async def create_template(
        self,
        name: str,
        content: str,
        description: str = None,
        category: str = "custom",
        is_locked: bool = False,
    ) -> Dict[str, Any]:
        data = {
            "name": name,
            "content": content,
            "description": description,
            "category": category,
            "is_locked": is_locked,
        }
        return self.client.table("templates").insert(data).execute().data[0]

    async def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        result = self.client.table("templates").select("*").eq("id", template_id).execute()
        return result.data[0] if result.data else None

    async def list_templates(self, category: str = None) -> List[Dict[str, Any]]:
        query = self.client.table("templates").select("*")
        if category:
            query = query.eq("category", category)
        return query.order("name").execute().data

    async def delete_template(self, template_id: str) -> bool:
        self.client.table("templates").delete().eq("id", template_id).eq("is_locked", False).execute()
        return True

    # ==================== CALL ANALYSIS ====================

    async def save_call_analysis(
        self,
        call_id: str,
        summary: str,
        key_points: List[str],
        user_sentiment: str,
        outcome: str,
        next_action: Optional[str] = None,
        intent_category: Optional[str] = None,
        budget_fit: Optional[str] = None,
        geography_fit: Optional[str] = None,
        timeline_fit: Optional[str] = None,
        overall_grade: Optional[str] = None,
        checkpoint_json: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        data = {
            "call_id": call_id,
            "summary": summary,
            "key_points": key_points,
            "user_sentiment": user_sentiment,
            "outcome": outcome,
            "next_action": next_action,
            "intent_category": intent_category,
            "budget_fit": budget_fit,
            "geography_fit": geography_fit,
            "timeline_fit": timeline_fit,
            "overall_grade": overall_grade,
            "checkpoint_json": checkpoint_json,
            "metadata": metadata or {},
            **kwargs,
        }
        clean_data = {k: v for k, v in data.items() if v is not None}
        try:
            return self.client.table("call_analysis").upsert(clean_data).execute().data[0]
        except Exception as write_error:
            error_text = str(write_error).lower()
            wow_fields = {
                "intent_category",
                "budget_fit",
                "geography_fit",
                "timeline_fit",
                "overall_grade",
                "checkpoint_json",
            }
            if "column" in error_text and "does not exist" in error_text:
                fallback = {k: v for k, v in clean_data.items() if k not in wow_fields}
                logger.warning("WOW columns missing in DB; saved base analysis only. Apply migration 011.")
                return self.client.table("call_analysis").upsert(fallback).execute().data[0]
            raise

    async def get_call_analysis(self, call_id: str) -> Optional[Dict[str, Any]]:
        result = self.client.table("call_analysis").select("*").eq("call_id", call_id).execute()
        return result.data[0] if result.data else None

    # ==================== KNOWLEDGE BASE ====================

    async def add_knowledge(
        self,
        agent_id: str,
        title: str,
        content: str,
        source_file: str = None,
        source_url: str = None,
        file_type: str = None,
        metadata: dict = None,
    ) -> Dict[str, Any]:
        data = {
            "agent_id": agent_id,
            "title": title,
            "content": content,
            "source_file": source_file,
            "source_url": source_url,
            "file_type": file_type,
            "metadata": metadata or {},
            "is_active": True,
        }
        return self.client.table("knowledge_base").insert(data).execute().data[0]

    async def get_agent_knowledge(self, agent_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        query = self.client.table("knowledge_base").select("*").eq("agent_id", agent_id)
        if active_only:
            query = query.eq("is_active", True)
        return query.order("created_at", desc=True).execute().data

    async def has_knowledge(self, agent_id: str) -> bool:
        result = (
            self.client.table("knowledge_base")
            .select("id")
            .eq("agent_id", agent_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        return len(result.data) > 0

    async def search_knowledge(self, agent_id: str, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        result = (
            self.client.table("knowledge_base")
            .select("*")
            .eq("agent_id", agent_id)
            .eq("is_active", True)
            .ilike("content", f"%{query}%")
            .execute()
        )
        return result.data[:limit] if result.data else []

    async def delete_knowledge(self, knowledge_id: str) -> bool:
        self.client.table("knowledge_base").delete().eq("id", knowledge_id).execute()
        return True

    async def update_knowledge(self, knowledge_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        result = self.client.table("knowledge_base").update(kwargs).eq("id", knowledge_id).execute()
        return result.data[0] if result.data else None

    async def get_usage_stats(self, user_id: str) -> Dict[str, Any]:
        try:
            count_result = self.client.table("calls").select("id", count="exact").eq("user_id", user_id).execute()
            total_calls = count_result.count if count_result.count is not None else 0

            duration_result = (
                self.client.table("calls")
                .select("duration")
                .eq("user_id", user_id)
                .not_.is_("duration", "null")
                .limit(1000)
                .execute()
            )
            total_seconds = sum((row.get("duration") or 0) for row in duration_result.data)
            return {
                "total_calls": total_calls,
                "total_minutes": round(total_seconds / 60, 1),
                "period": "all_time",
            }
        except Exception as e:
            logger.error(f"Error fetching usage stats: {e}")
            return {"total_calls": 0, "total_minutes": 0, "period": "error"}


# Global instance
_db_instance: Optional[RelayDB] = None
# Backward-compat global expected by some routes (e.g., event_routes import).
db: Optional[RelayDB] = None


def get_db() -> RelayDB:
    global _db_instance, db
    if _db_instance is None:
        _db_instance = RelayDB()
        db = _db_instance
    elif db is None:
        db = _db_instance
    return _db_instance

