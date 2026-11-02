CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL CHECK (length(full_name) BETWEEN 2 AND 100),
    email TEXT NOT NULL CHECK (length(email) BETWEEN 3 AND 150),
    phone TEXT NOT NULL CHECK (length(phone) BETWEEN 7 AND 30),
    category TEXT NOT NULL CHECK (category IN ('Family', 'Friends', 'Work', 'Others')),
    address TEXT NOT NULL DEFAULT '' CHECK (length(address) <= 250),
    notes TEXT NOT NULL DEFAULT '' CHECK (length(notes) <= 500),
    added_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_contacts_added_at ON contacts (added_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_contacts_category ON contacts (category);
