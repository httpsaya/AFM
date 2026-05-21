from fastapi import APIRouter, HTTPException, Query
from api.database import get_conn
from typing import Optional
from thefuzz import fuzz

router = APIRouter()


@router.get("/counterparty/{id}")
def get_counterparty(id: str):
    conn = get_conn()
    try:
        row = conn.execute("""
            SELECT
                COUNT(*) AS tx_count,
                ROUND(SUM(amount_kzt), 2) AS total_turnover,
                ROUND(SUM(CASE WHEN sender_id = ? THEN amount_kzt ELSE 0 END), 2) AS outgoing,
                ROUND(SUM(CASE WHEN receiver_id = ? THEN amount_kzt ELSE 0 END), 2) AS incoming
            FROM transactions
            WHERE sender_id = ? OR receiver_id = ?
        """, (id, id, id, id)).fetchone()

        if row["tx_count"] == 0:
            raise HTTPException(status_code=404, detail=f"Counterparty {id} not found")

        partners = conn.execute("""
            SELECT
                CASE WHEN sender_id = ? THEN receiver_id ELSE sender_id END AS partner_id,
                COUNT(*) AS tx_count,
                ROUND(SUM(amount_kzt), 2) AS total_kzt
            FROM transactions
            WHERE sender_id = ? OR receiver_id = ?
            GROUP BY partner_id
            ORDER BY total_kzt DESC
            LIMIT 3
        """, (id, id, id)).fetchall()

        monthly = conn.execute("""
            SELECT
                STRFTIME('%Y-%m', date) AS month,
                COUNT(*) AS tx_count,
                ROUND(SUM(amount_kzt), 2) AS total_kzt
            FROM transactions
            WHERE sender_id = ? OR receiver_id = ?
            GROUP BY month
            ORDER BY month
        """, (id, id)).fetchall()

        return {
            "id": id,
            "tx_count": row["tx_count"],
            "total_turnover": row["total_turnover"],
            "outgoing": row["outgoing"],
            "incoming": row["incoming"],
            "top_partners": [dict(p) for p in partners],
            "monthly": [dict(m) for m in monthly],
        }
    finally:
        conn.close()


@router.get("/search")
def search(
    q: str = Query(..., min_length=1),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    amount_min: Optional[float] = Query(None),
    amount_max: Optional[float] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    conn = get_conn()
    try:
        filters = ["description IS NOT NULL"]
        params  = []

        if date_from:
            filters.append("date >= ?")
            params.append(date_from)
        if date_to:
            filters.append("date <= ?")
            params.append(date_to)
        if amount_min is not None:
            filters.append("amount_kzt >= ?")
            params.append(amount_min)
        if amount_max is not None:
            filters.append("amount_kzt <= ?")
            params.append(amount_max)

        where = " AND ".join(filters)

        rows = conn.execute(
            f"""
            SELECT sender_id, receiver_id, date, amount_kzt, description, doc_type
            FROM transactions
            WHERE {where}
            ORDER BY date DESC
            """,
            params,
        ).fetchall()

        results = []
        for r in rows:
            desc = r["description"] or ""
            score = fuzz.partial_ratio(q.lower(), desc.lower())
            if score >= 60:
                results.append({**dict(r), "match_score": score})

        results.sort(key=lambda x: x["match_score"], reverse=True)

        total  = len(results)
        offset = (page - 1) * page_size
        page_results = results[offset: offset + page_size]

        return {
            "query": q,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
            "results": page_results,
        }
    finally:
        conn.close()


@router.get("/counterparty/{id}/anomalies")
def get_anomalies(id: str):
    conn = get_conn()
    try:
        exists = conn.execute("""
            SELECT COUNT(*) AS cnt FROM transactions
            WHERE sender_id = ? OR receiver_id = ?
        """, (id, id)).fetchone()["cnt"]

        if exists == 0:
            raise HTTPException(status_code=404, detail=f"Counterparty {id} not found")

        anomalies = []

        concentration = conn.execute("""
            WITH pair AS (
                SELECT sender_id, SUM(amount_kzt) AS pair_total
                FROM transactions
                WHERE receiver_id = ? AND amount_kzt > 0
                GROUP BY sender_id
            ),
            total AS (
                SELECT SUM(amount_kzt) AS grand_total
                FROM transactions
                WHERE receiver_id = ? AND amount_kzt > 0
            )
            SELECT
                p.sender_id,
                ROUND(p.pair_total, 2) AS pair_total,
                ROUND(t.grand_total, 2) AS grand_total,
                ROUND(p.pair_total * 100.0 / t.grand_total, 1) AS share_pct
            FROM pair p, total t
            ORDER BY share_pct DESC
            LIMIT 1
        """, (id, id)).fetchone()

        if concentration and concentration["share_pct"] > 70:
            anomalies.append({
                "type": "high_concentration",
                "description": f"{concentration['share_pct']}% incoming from one source",
                "details": dict(concentration),
            })

        spikes = conn.execute("""
            WITH monthly AS (
                SELECT
                    STRFTIME('%Y-%m', date) AS month,
                    SUM(ABS(amount_kzt)) AS total
                FROM transactions
                WHERE sender_id = ? OR receiver_id = ?
                GROUP BY month
            ),
            stats AS (
                SELECT
                    AVG(total) AS mean,
                    AVG(total * total) - AVG(total) * AVG(total) AS variance
                FROM monthly
            )
            SELECT m.month, ROUND(m.total, 2) AS total,
                   ROUND(s.mean, 2) AS mean
            FROM monthly m, stats s
            WHERE m.total > s.mean + 2 * SQRT(MAX(s.variance, 0))
            ORDER BY m.total DESC
        """, (id, id)).fetchall()

        if spikes:
            anomalies.append({
                "type": "turnover_spike",
                "description": f"{len(spikes)} months with abnormally high turnover detected",
                "details": [dict(s) for s in spikes],
            })

        negatives = conn.execute("""
            SELECT COUNT(*) AS cnt, ROUND(SUM(amount_kzt), 2) AS total
            FROM transactions
            WHERE (sender_id = ? OR receiver_id = ?) AND amount_kzt < 0
        """, (id, id)).fetchone()

        if negatives["cnt"] > 0:
            anomalies.append({
                "type": "negative_amounts",
                "description": f"{negatives['cnt']} transactions with negative amounts",
                "details": dict(negatives),
            })

        return {
            "id": id,
            "anomalies": anomalies,
            "total": len(anomalies),
        }
    finally:
        conn.close()
