-- Schema
CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    company TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    tier TEXT DEFAULT 'standard' CHECK (tier IN ('standard', 'premium', 'enterprise')),
    account_manager TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS issues (
    id SERIAL PRIMARY KEY,
    customer_id INT REFERENCES customers(id),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'resolved', 'closed')),
    priority TEXT DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS issue_updates (
    id SERIAL PRIMARY KEY,
    issue_id INT REFERENCES issues(id),
    author TEXT NOT NULL,
    note TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS next_actions (
    id SERIAL PRIMARY KEY,
    issue_id INT REFERENCES issues(id),
    action TEXT NOT NULL,
    assigned_to TEXT,
    due_date DATE,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'cancelled')),
    created_by TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT,
    role TEXT NOT NULL CHECK (role IN ('sales_user', 'support_user', 'admin'))
);

-- Seed data
INSERT INTO customers (name, company, email, phone, tier, account_manager) VALUES
('Alice Johnson', 'TechCorp Ltd', 'alice@techcorp.com', '+44 20 1234 5678', 'enterprise', 'Bob Smith'),
('David Lee', 'RetailMax PLC', 'david@retailmax.com', '+44 20 2345 6789', 'premium', 'Carol White'),
('Emma Davis', 'HealthPlus Ltd', 'emma@healthplus.com', '+44 20 3456 7890', 'standard', 'Bob Smith'),
('Frank Chen', 'FinServe Group', 'frank@finserve.com', '+44 20 4567 8901', 'enterprise', 'Carol White'),
('Grace Kim', 'EduTech Co', 'grace@edutech.com', '+44 20 5678 9012', 'standard', 'Bob Smith');

INSERT INTO issues (customer_id, title, description, status, priority) VALUES
(1, 'API rate limiting causing failures', 'Intermittent 429 errors on the data-export endpoint since 2025-05-01', 'open', 'critical'),
(1, 'SSO integration broken after upgrade', 'Users cannot log in via SSO following v4.2 upgrade', 'in_progress', 'high'),
(2, 'Bulk import timeout', 'CSV imports larger than 50k rows fail with a timeout after ~2 minutes', 'open', 'high'),
(3, 'Dashboard widgets not loading', 'Three widgets on the analytics dashboard show a spinner indefinitely', 'open', 'medium'),
(4, 'Compliance report generation error', 'PDF export for Q1 compliance report returns 500 error', 'open', 'critical'),
(4, 'Data retention policy misconfigured', 'Records older than 7 years are not being purged per policy', 'in_progress', 'high'),
(5, 'Email notifications delayed', 'Students receiving assignment alerts 6-12 hours late', 'open', 'medium');

INSERT INTO issue_updates (issue_id, author, note) VALUES
(1, 'Bob Smith', 'Escalated to engineering. Root cause suspected to be misconfigured throttle limits on the gateway.'),
(1, 'Engineering', 'Identified that the rate-limit bucket size is set to 100 instead of 1000. Patch scheduled for Friday.'),
(2, 'Carol White', 'Initial call with client. SSO provider is Okta. Shared debug logs with L2 team.'),
(2, 'L2 Support', 'Confirmed callback URL mismatch. Fix applied in staging, awaiting client sign-off.'),
(3, 'Ops Team', 'Raised with RetailMax. Provided workaround: split imports into batches of 10k rows.'),
(4, 'Bob Smith', 'Reproduced locally. Spinner appears when widget API returns null dataset.'),
(5, 'Engineering', 'Stack trace shows null pointer in PDF renderer. Likely a data formatting issue in Q1 dataset.'),
(6, 'Carol White', 'Policy config reviewed. Retention job was disabled during December maintenance window and not re-enabled.'),
(7, 'Bob Smith', 'Email queue depth is normal. Investigating SMTP relay latency with infrastructure team.');

INSERT INTO next_actions (issue_id, action, assigned_to, due_date, status, created_by) VALUES
(1, 'Deploy rate-limit patch to production gateway', 'Engineering', '2025-05-10', 'pending', 'admin'),
(1, 'Notify TechCorp of scheduled maintenance window', 'Bob Smith', '2025-05-08', 'pending', 'admin'),
(2, 'Obtain Okta configuration from TechCorp IT team', 'Carol White', '2025-05-09', 'done', 'admin'),
(3, 'Provide interim workaround documentation to RetailMax', 'Bob Smith', '2025-05-07', 'done', 'admin'),
(5, 'Fix null pointer in PDF renderer and redeploy', 'Engineering', '2025-05-11', 'pending', 'admin'),
(6, 'Re-enable retention job and verify purge on test dataset', 'Ops Team', '2025-05-09', 'pending', 'admin');

INSERT INTO users (username, email, role) VALUES
('alice_sales', 'alice_sales@acme.internal', 'sales_user'),
('bob_support', 'bob_support@acme.internal', 'support_user'),
('carol_admin', 'carol_admin@acme.internal', 'admin');
