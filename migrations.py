async def m001_initial(db):
    await db.execute("""
        CREATE TABLE zapgoals.goals (
            id TEXT PRIMARY KEY,
            wallet TEXT NOT NULL,
            title TEXT NOT NULL,
            description_above TEXT NOT NULL DEFAULT '',
            description_below TEXT NOT NULL DEFAULT '',
            goal_amount INTEGER NOT NULL,
            target_date TIMESTAMP NOT NULL,
            current_amount INTEGER NOT NULL DEFAULT 0,
            wallet_mode TEXT NOT NULL DEFAULT 'vanilla',
            background_color TEXT NOT NULL DEFAULT '#FFFFFF',
            text_color TEXT NOT NULL DEFAULT '#111111',
            progress_color TEXT NOT NULL DEFAULT '#2E7D32',
            remainder_color TEXT NOT NULL DEFAULT '#E0E0E0',
            font_family TEXT NOT NULL DEFAULT 'sans-serif',
            nostr_pubkey TEXT,
            lightning_address_username TEXT UNIQUE,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            CHECK (goal_amount > 0),
            CHECK (current_amount >= 0),
            CHECK (wallet_mode IN ('vanilla', 'nwc', 'all')),
            CHECK (font_family IN ('sans-serif', 'serif', 'monospace'))
        )
        """)
    await db.execute("""
        CREATE TABLE zapgoals.contributions (
            payment_hash TEXT PRIMARY KEY,
            goal_id TEXT NOT NULL,
            amount INTEGER NOT NULL,
            paid BOOLEAN NOT NULL DEFAULT FALSE,
            source TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL,
            paid_at TIMESTAMP,
            CHECK (amount > 0),
            CHECK (source IN ('invoice', 'lnurl', 'nostr'))
        )
        """)
    table = f"{db.references_schema}contributions"
    await db.execute(
        f"CREATE INDEX zapgoals_contributions_goal_idx ON {table} (goal_id, paid)"
    )
    await db.execute("""
        CREATE TABLE zapgoals.settings (
            id TEXT PRIMARY KEY,
            nostr_private_key TEXT NOT NULL
        )
        """)
