"""Read-only inspection of one user's new-service logs; no credentials required."""
import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path


def positive(value):
    number=int(value)
    if number<1:raise argparse.ArgumentTypeError("양의 정수를 입력해 주세요.")
    return number


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db",type=Path,required=True)
    parser.add_argument("--user-id",type=positive,required=True)
    parser.add_argument("--limit",type=positive,default=20)
    args=parser.parse_args()
    if args.limit>100:parser.error("limit은 100 이하여야 합니다.")
    if not args.db.is_file():parser.error("DB 파일이 존재하지 않습니다.")
    sql="""SELECT t.id, t.conversation_id, t.user_id, t.created_at,
                  t.question, t.answer, t.status, t.error_code, t.request_id
           FROM reels_turns AS t
           JOIN reels_conversations AS c ON c.id = t.conversation_id
           WHERE t.user_id = ? AND c.user_id = ? ORDER BY t.id DESC LIMIT ?"""
    try:
        with closing(sqlite3.connect(args.db.resolve().as_uri()+"?mode=ro",uri=True)) as db:
            db.row_factory=sqlite3.Row
            rows=[dict(row) for row in db.execute(sql,(args.user_id,args.user_id,args.limit))]
        print(json.dumps(rows,ensure_ascii=False,indent=2))
    except sqlite3.Error as exc:
        print(f"DB 확인 실패: {type(exc).__name__}",file=sys.stderr)
        return 1
    return 0


if __name__=="__main__":
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
