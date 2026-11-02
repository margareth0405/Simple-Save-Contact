# ContactHub EC2 deployment guide

These files prepare an Ubuntu EC2 host for ContactHub. They do not create an EC2 instance or publish this project automatically. The example Nginx configuration serves a public-IP HTTP **demonstration**. It should contain fictional contacts only. Add authentication and HTTPS before storing real personal information.

## 1. Prepare the instance

Use an Ubuntu EC2 instance with a public IPv4 address. In its security group, allow inbound TCP 80 from visitors and TCP 22 only from your own IP address. Do not open port 8000; Gunicorn will listen on loopback. Add TCP 443 when HTTPS is configured. AWS describes these rules in its [EC2 security group guidance](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-rules-reference.html).

Connect to the instance with SSH and install the packages:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx
```

Transfer the `contacthub/` source directory to `/home/ubuntu/contacthub` by your preferred secure method. Do not transfer local SQLite files, `.env` files, or `.venv` directories.

## 2. Install the application

```bash
sudo useradd --system --home-dir /var/lib/contacthub --shell /usr/sbin/nologin contacthub
sudo install -d -o contacthub -g contacthub -m 750 /var/lib/contacthub
sudo install -d -o contacthub -g contacthub -m 755 /srv/contacthub
sudo cp -a /home/ubuntu/contacthub/. /srv/contacthub/
sudo chown -R contacthub:contacthub /srv/contacthub
cd /srv/contacthub
sudo -u contacthub python3 -m venv .venv
sudo -u contacthub .venv/bin/pip install -r requirements.txt
```

If `useradd` says the account already exists, verify it is the intended service account and continue without recreating it.

Create a private service environment file:

```bash
sudo install -d -o root -g contacthub -m 750 /etc/contacthub
sudo install -o root -g contacthub -m 640 .env.example /etc/contacthub/contacthub.env
sudoedit /etc/contacthub/contacthub.env
```

Replace the example secret with a long random value, set `CONTACTHUB_TRUSTED_HOSTS` to the actual public IP or DNS name, and leave `CONTACTHUB_DATABASE=/var/lib/contacthub/contacthub.sqlite3`. For the HTTP public-IP demonstration, keep `CONTACTHUB_SECURE_COOKIE=false`. When serving over HTTPS, change it to `true` and restart the service. Do not commit or share the filled environment file.

Initialize the database and optionally add five fictional contacts:

```bash
sudo -u contacthub env CONTACTHUB_DATABASE=/var/lib/contacthub/contacthub.sqlite3 .venv/bin/flask --app app init-db
sudo -u contacthub env CONTACTHUB_DATABASE=/var/lib/contacthub/contacthub.sqlite3 .venv/bin/flask --app app seed-demo
```

`init-db` is safe to rerun. `seed-demo` adds records only if the database is empty.

## 3. Run Gunicorn and Nginx

Flask recommends a production WSGI server behind a reverse proxy; its [Gunicorn](https://flask.palletsprojects.com/en/stable/deploying/gunicorn/) and [Nginx](https://flask.palletsprojects.com/en/stable/deploying/nginx/) guides describe the pattern used here.

```bash
sudo cp deploy/contacthub.service /etc/systemd/system/contacthub.service
sudo systemctl daemon-reload
sudo systemctl enable --now contacthub
sudo systemctl status contacthub --no-pager
sudo cp deploy/contacthub.nginx.conf /etc/nginx/sites-available/contacthub
sudoedit /etc/nginx/sites-available/contacthub
sudo ln -s /etc/nginx/sites-available/contacthub /etc/nginx/sites-enabled/contacthub
sudo nginx -t
sudo systemctl reload nginx
```

In the Nginx configuration, replace `YOUR_EC2_PUBLIC_IP` before reloading. If the Ubuntu default site responds instead, disable its `sites-enabled/default` entry and reload Nginx after `nginx -t` succeeds.

## 4. Verify the live instance

On the instance:

```bash
curl -I http://127.0.0.1:8000/
curl -I http://127.0.0.1/
curl -I http://127.0.0.1/static/css/style.css
sudo journalctl -u contacthub -n 50 --no-pager
```

From your computer, visit `http://YOUR_EC2_PUBLIC_IP/`. Confirm the dashboard and contacts page load, then create, edit, search, filter, and delete a fictional contact. Refresh after each change to confirm SQLite persistence. A successful local test does not verify EC2 until these live checks pass.

## Operations

- SQLite files live under `/var/lib/contacthub/`, outside the served source directory. Back up the database before replacing the instance or updating the schema.
- Run `python -m unittest discover -s tests -v` before deploying new code.
- Use `sudo journalctl -u contacthub -f` for app startup errors and `/var/log/nginx/error.log` for proxy or static-file problems.
- If the session cookie is marked secure while the page is served over HTTP, create/edit/delete requests will fail CSRF validation. Set `CONTACTHUB_SECURE_COOKIE=false` only for the fictional-data HTTP demonstration, or configure HTTPS.
- ContactHub has no user accounts or authorization yet. Its API is public to anyone who can reach the site. Use fictional data until access controls and HTTPS are added.
