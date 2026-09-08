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


async def m002_suggested_amounts_and_wallet_modes(db):
    await db.execute("""
        ALTER TABLE zapgoals.goals
        ADD COLUMN suggested_amounts TEXT NOT NULL DEFAULT '[21,100,500,1000]'
        """)
    await db.execute("""
        UPDATE zapgoals.goals SET wallet_mode = 'all' WHERE wallet_mode = 'nwc'
        """)


async def m003_font_name_and_weight(db):
    await db.execute("""
        ALTER TABLE zapgoals.goals
        ADD COLUMN font_name TEXT NOT NULL DEFAULT 'sans-serif'
        """)
    await db.execute("""
        ALTER TABLE zapgoals.goals
        ADD COLUMN font_weight INTEGER NOT NULL DEFAULT 400
        """)
    await db.execute("UPDATE zapgoals.goals SET font_name = font_family")


async def m004_recurring(db):
    await db.execute("""
        ALTER TABLE zapgoals.goals
        ADD COLUMN recurring BOOLEAN NOT NULL DEFAULT FALSE
        """)
    await db.execute("""
        ALTER TABLE zapgoals.goals
        ADD COLUMN recurrence_unit TEXT
        """)
    await db.execute("""
        ALTER TABLE zapgoals.goals
        ADD COLUMN recurrence_interval INTEGER NOT NULL DEFAULT 1
        """)
    await db.execute("""
        ALTER TABLE zapgoals.goals
        ADD COLUMN recurrence_day_of_month INTEGER
        """)
    await db.execute("""
        ALTER TABLE zapgoals.goals
        ADD COLUMN target_wallet_id TEXT
        """)
    await db.execute("""
        ALTER TABLE zapgoals.goals
        ADD COLUMN rollover_mode TEXT NOT NULL DEFAULT 'counts_as_progress'
        """)
    await db.execute("""
        ALTER TABLE zapgoals.goals
        ADD COLUMN sweep_mode TEXT NOT NULL DEFAULT 'target_amount'
        """)
    await db.execute("""
        ALTER TABLE zapgoals.goals
        ADD COLUMN period_index INTEGER NOT NULL DEFAULT 0
        """)
    await db.execute("""
        ALTER TABLE zapgoals.goals
        ADD COLUMN period_start TIMESTAMP
        """)
    await db.execute("""
        ALTER TABLE zapgoals.goals
        ADD COLUMN last_swept_at TIMESTAMP
        """)
    await db.execute("""
        ALTER TABLE zapgoals.goals
        ADD COLUMN sweeping BOOLEAN NOT NULL DEFAULT FALSE
        """)
    await db.execute("""
        CREATE TABLE zapgoals.periods (
            id TEXT PRIMARY KEY,
            goal_id TEXT NOT NULL,
            period_index INTEGER NOT NULL,
            period_start TIMESTAMP NOT NULL,
            period_end TIMESTAMP NOT NULL,
            zapped_total INTEGER NOT NULL,
            moved_to_target INTEGER NOT NULL,
            rollover INTEGER NOT NULL,
            sweep_mode TEXT NOT NULL,
            swept_at TIMESTAMP NOT NULL,
            CHECK (zapped_total >= 0),
            CHECK (moved_to_target >= 0),
            CHECK (rollover >= 0),
            CHECK (sweep_mode IN ('target_amount', 'entire_amount')),
            UNIQUE (goal_id, period_index)
        )
        """)
    table = f"{db.references_schema}periods"
    await db.execute(
        f"CREATE INDEX zapgoals_periods_goal_idx ON {table} (goal_id, period_index)"
    )


async def m005_public_period_badge(db):
    await db.execute("""
        ALTER TABLE zapgoals.goals
        ADD COLUMN show_period_badge BOOLEAN NOT NULL DEFAULT TRUE
        """)
