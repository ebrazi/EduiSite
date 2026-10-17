from flask import Blueprint, render_template, current_app

bp = Blueprint("public", __name__)


@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/robots.txt")
def robots():
    lines = ["User-agent: *"]
    for path in ("/dashboard", "/book", "/wallet", "/register", "/login",
                 "/admin", "/mock-gateway", "/payment"):
        lines.append(f"Disallow: {path}")
    lines.append(f"Sitemap: {current_app.config['SITE_URL']}/sitemap.xml")
    return "\n".join(lines) + "\n", 200, {"Content-Type": "text/plain; charset=utf-8"}


@bp.route("/sitemap.xml")
def sitemap():
    base = current_app.config["SITE_URL"]
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{base}/</loc><changefreq>weekly</changefreq></url>\n"
        "</urlset>\n"
    )
    return xml, 200, {"Content-Type": "application/xml; charset=utf-8"}
