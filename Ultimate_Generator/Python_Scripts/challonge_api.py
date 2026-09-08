#!/usr/bin/env python3
"""Shared Challonge API v2.1 client for the two Challonge fetchers.

Unlike the parry.gg pair, which duplicate their small helpers, the Challonge
scripts share this module: both need the same auth headers, the same pagination
loop and the same tolerant JSON:API accessors, and getting any of those subtly
different between the two would show up as one fetcher working and the other
quietly returning nothing.

Auth
----
Two paths, tried in that order:

**OAuth client credentials** (the current one). Challonge's developer portal no
longer issues bare v1 keys -- it issues an application, with a **client id** and
a **client secret**. Of the three OAuth flows the API offers, client credentials
is the only one that suits a desktop tool: authorization-code needs a redirect
URL and a browser round trip, and the device grant needs a second device. The
docs describe the client-credentials token as covering "tournaments organized by
the application's owner", which is exactly this case -- the person running the
generator is the person whose brackets are being read.

``challonge.client.id`` and ``challonge.client.secret`` go in ``app.properties``.
The access token is short-lived, so it is cached next to that file in
``.challonge_token.json`` and re-minted when it expires; nothing about the flow
needs a browser or user interaction.

**A legacy v1 key**, still accepted by v2.1 through two headers
(``Authorization-Type: v1`` and ``Authorization: <key>``). Kept because accounts
issued one before the portal changed can still use it: set
``challonge.api.key`` and it wins over the client credentials.

Run this module directly to check whichever credentials are configured::

    py -3.12 challonge_api.py

Response shape
--------------
v2.1 follows JSON:API: a resource is ``{"id": ..., "type": ..., "attributes":
{...}, "relationships": {...}}``. The published v2.1 reference is incomplete in
places (several of its "v2.1" pages still serve the deprecated v1 spec), so
:func:`attrs` and :func:`rel_id` also accept the flat v1 shape -- ``player1_id``
sitting directly on the object rather than under ``relationships``. That costs
nothing when the response is well formed and means an unannounced shape change
degrades instead of raising ``AttributeError`` halfway through a fetch. Run
either fetcher with ``--debug`` to dump what actually came back.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

import requests

BASE_URL = "https://api.challonge.com/v2.1"
TOKEN_URL = "https://api.challonge.com/oauth/token"

#: Sent on every request. Challonge sits behind Cloudflare, which answers
#: requests' default "python-requests/x.y" agent with an HTTP 520 ("origin
#: returned an unknown error") on both the token endpoint and the API -- not a
#: 403, so it reads as Challonge being broken rather than as us being filtered.
#: Any ordinary-looking agent string is accepted; the value itself is not
#: checked. Never drop this header.
USER_AGENT = "GraphicGenerator/1.0 (+https://challonge.com)"
REQUEST_TIMEOUT = 20.0
#: Challonge's own default is 25; the ceiling is undocumented, and 100 is what
#: the v1 API accepted. A page short of this size ends the pagination loop.
PAGE_SIZE = 100

CLIENT_ID_PROPERTY = "challonge.client.id"
CLIENT_SECRET_PROPERTY = "challonge.client.secret"
API_KEY_PROPERTY = "challonge.api.key"

DEVELOPER_PORTAL = "https://challonge.com/settings/developer"

#: Scopes to ask the token endpoint for, most-preferred first. The published
#: reference does not say which scopes the client-credentials grant will issue
#: -- it lists "me tournaments:read matches:read participants:read ..." in one
#: place and an "application:manage" that is documented as client-credentials
#: only in another -- so the least-privileged read set is tried first, then the
#: server's own default (no scope parameter), then the broad one. Whichever is
#: granted is reported, so there is no guessing about what a token can do.
_SCOPE_LADDER = [
    "me tournaments:read matches:read participants:read",
    None,
    "application:manage",
]

# app.properties lives two levels up from this script (Graphic Generator root),
# the same place the start.gg and parry.gg keys are read from.
_SCRIPT_DIR = Path(__file__).resolve().parent
PROPS_FILE = str(_SCRIPT_DIR.parent.parent / "app.properties")
#: Cached access token, beside app.properties and gitignored the same way. A
#: fetch is a separate process, so without this every run would mint a new
#: token; the file holds a bearer credential and nothing else.
TOKEN_CACHE_FILE = str(_SCRIPT_DIR.parent.parent / ".challonge_token.json")

#: A Challonge URL, with the scheme optional (a slug is routinely pasted
#: without one) and the community subdomain captured -- an organisation's
#: bracket lives at "myorg.challonge.com/slug" as well as at
#: "challonge.com/myorg/slug", and both address the same tournament.
_URL_RE = re.compile(
    r'^(?:https?://)?(?:(?P<sub>[A-Za-z0-9_-]+)\.)?challonge\.com/', re.I)

#: Path segments that are part of the bracket *view*, not of the tournament
#: identifier. A copied URL is routinely one of these ("/module", "/standings"),
#: and Challonge's own subdomain tournaments are "challonge.com/<sub>/<slug>",
#: so the segment after the slug cannot simply be assumed to be a subdomain.
_VIEW_SEGMENTS = {
    "module", "standings", "log", "matches", "participants", "groups",
    "settings", "edit", "bracket", "brackets", "teams", "predictions",
}


def load_properties(props_path: str = PROPS_FILE) -> dict:
    """The ``key = value`` pairs in app.properties, comments skipped."""
    values: dict = {}
    try:
        with open(props_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                key, sep, val = line.partition("=")
                if sep:
                    values[key.strip()] = val.strip()
    except FileNotFoundError:
        pass
    return values


class Credentials:
    """What app.properties says about Challonge, and how to authorize with it.

    An instance is what the fetchers pass around in place of the bare API-key
    string the parry scripts use, because OAuth needs somewhere to keep the
    minted token for the life of the process.
    """

    def __init__(self, api_key: str = "", client_id: str = "",
                 client_secret: str = "", cache_path: str = TOKEN_CACHE_FILE):
        self.api_key = api_key
        self.client_id = client_id
        self.client_secret = client_secret
        self.cache_path = cache_path
        self._token = ""
        self._scope = ""

    def __bool__(self) -> bool:
        return bool(self.api_key or (self.client_id and self.client_secret))

    @property
    def kind(self) -> str:
        if self.api_key:
            return "v1 key"
        if self.client_id and self.client_secret:
            return "OAuth client credentials"
        return "none"

    @property
    def scope(self) -> str:
        """The scope the current token was granted, once one has been minted."""
        return self._scope

    # -- token cache ------------------------------------------------------
    #
    # Keyed by client id so that changing the id in app.properties cannot
    # silently keep using the old application's token, and stored with an
    # absolute expiry rather than the API's relative "expires_in".

    def _read_cache(self) -> str:
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                blob = json.load(f)
        except (OSError, ValueError):
            return ""
        if blob.get("client_id") != self.client_id:
            return ""
        # A minute of slack, so a token that expires mid-fetch is renewed now
        # rather than failing the request that happens to straddle it.
        if float(blob.get("expires_at") or 0) <= time.time() + 60:
            return ""
        self._scope = blob.get("scope") or ""
        return blob.get("access_token") or ""

    def _write_cache(self, token: str, expires_in, scope: str) -> None:
        try:
            expiry = time.time() + float(expires_in)
        except (TypeError, ValueError):
            expiry = time.time() + 3600
        blob = {"client_id": self.client_id, "access_token": token,
                "expires_at": expiry, "scope": scope}
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(blob, f)
        except OSError:
            # A cache that cannot be written is not a failure -- the token is
            # good for this process, and the next run mints another.
            pass

    # -- OAuth ------------------------------------------------------------

    def _request_token(self, scope: Optional[str]) -> tuple:
        """``(token, expires_in, scope, error)`` for one scope attempt."""
        body = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        if scope:
            body["scope"] = scope
        r = requests.post(
            TOKEN_URL, data=body, timeout=REQUEST_TIMEOUT,
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Accept": "application/json",
                     "User-Agent": USER_AGENT})
        try:
            payload = r.json()
        except ValueError:
            payload = {}
        if r.status_code == 200 and payload.get("access_token"):
            return (payload["access_token"], payload.get("expires_in"),
                    payload.get("scope") or (scope or ""), "")
        detail = (payload.get("error_description") or payload.get("error")
                  or r.text[:200])
        return "", None, "", f"HTTP {r.status_code}: {detail}"

    def token(self) -> str:
        """A bearer token, from the cache or freshly minted."""
        if self._token:
            return self._token
        cached = self._read_cache()
        if cached:
            self._token = cached
            return cached

        errors = []
        for scope in _SCOPE_LADDER:
            token, expires_in, granted, error = self._request_token(scope)
            if token:
                self._token = token
                self._scope = granted
                self._write_cache(token, expires_in, granted)
                return token
            errors.append(f"  scope={scope or '(server default)'} -> {error}")
        raise RuntimeError(
            "Challonge refused the client credentials. Check "
            f"{CLIENT_ID_PROPERTY} and {CLIENT_SECRET_PROPERTY} in "
            f"app.properties against {DEVELOPER_PORTAL}. The token endpoint "
            "said:\n" + "\n".join(errors))

    # -- request headers --------------------------------------------------

    def headers(self) -> dict:
        base = {
            "Content-Type": "application/vnd.api+json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        if self.api_key:
            base["Authorization-Type"] = "v1"
            base["Authorization"] = self.api_key
        else:
            # "v2", not "Bearer". Challonge reads this header to pick a
            # scheme and rejects an unrecognised value with a bodyless 401,
            # which looks exactly like a bad token -- the standard
            # "Authorization: Bearer ..." header alone is not enough.
            base["Authorization-Type"] = "v2"
            base["Authorization"] = f"Bearer {self.token()}"
        return base


def load_credentials(props_path: str = PROPS_FILE) -> Credentials:
    """Challonge credentials from app.properties.

    A legacy v1 key wins when one is set, because an account that still has one
    can use it directly and skip the token round trip entirely.
    """
    props = load_properties(props_path)
    return Credentials(
        api_key=props.get(API_KEY_PROPERTY, ""),
        client_id=props.get(CLIENT_ID_PROPERTY, ""),
        client_secret=props.get(CLIENT_SECRET_PROPERTY, ""),
    )


def missing_credentials_message(props_path: str = PROPS_FILE) -> str:
    """What to tell the user when nothing is configured."""
    return (
        f"No Challonge credentials in {props_path}.\n"
        f"Create an application at {DEVELOPER_PORTAL}, then add:\n"
        f"  {CLIENT_ID_PROPERTY} = <your client id>\n"
        f"  {CLIENT_SECRET_PROPERTY} = <your client secret>\n"
        f"(An older account with a v1 API key may set {API_KEY_PROPERTY} "
        f"instead.)")


def normalize_slug(value: str) -> str:
    """Reduce a pasted Challonge URL to the identifier the API addresses.

    Challonge addresses a **tournament**, like parry.gg and unlike start.gg,
    and the identifier is its URL slug::

        https://challonge.com/abc123          -> abc123
        https://challonge.com/abc123/module   -> abc123

    A tournament hosted under a community (organisation) subdomain is
    ``challonge.com/<subdomain>/<slug>``, and v2.1 addresses it with the two
    joined by a hyphen -- ``<subdomain>-<slug>`` -- which is also how the
    subdomain form is written in the docs. The second segment is only treated
    as the slug when it is not one of the bracket *view* pages a copied URL
    tends to end in; ``challonge.com/abc123/standings`` is one tournament, not
    a community called abc123.
    """
    text = (value or "").strip()
    match = _URL_RE.match(text)
    subdomain = ""
    if match:
        text = text[match.end():]
        sub = (match.group("sub") or "").lower()
        if sub and sub != "www":
            subdomain = sub
    text = text.split("?")[0].split("#")[0].strip("/")
    if not text:
        return ""
    parts = [p for p in text.split("/") if p]
    if subdomain:
        return f"{subdomain}-{parts[0]}"
    if len(parts) >= 2 and parts[1].lower() not in _VIEW_SEGMENTS:
        return f"{parts[0]}-{parts[1]}"
    return parts[0]


def challonge_get(path: str, creds: Credentials,
                  params: Optional[dict] = None) -> dict:
    """GET one v2.1 endpoint, raising with the server's own message on failure.

    The error text matters: bad credentials come back as 401, a token without
    the right scope as 403, and a tournament the account cannot see as 404 --
    and those are the three things that actually go wrong.
    """
    url = f"{BASE_URL}/{path.lstrip('/')}"
    r = requests.get(url, headers=creds.headers(), params=params or {},
                     timeout=REQUEST_TIMEOUT)
    if r.status_code == 401:
        raise RuntimeError(
            f"Challonge rejected the credentials (HTTP 401), authorizing with "
            f"{creds.kind}. Check app.properties against {DEVELOPER_PORTAL}."
        )
    if r.status_code == 403:
        raise RuntimeError(
            f"Challonge refused access to {path} (HTTP 403). The token was "
            f"granted scope {creds.scope or '(none reported)'}, which does not "
            f"cover this. If the tournament was not created through this "
            f"application, it may not be visible to a client-credentials "
            f"token at all."
        )
    if r.status_code == 404:
        raise RuntimeError(
            f"Challonge has no tournament at {url} (HTTP 404). Check the slug, "
            "and note that a private tournament is only visible to the account "
            "the API key belongs to."
        )
    if r.status_code != 200:
        raise RuntimeError(
            f"Request to {path} failed (HTTP {r.status_code}): {r.text[:200]}")
    try:
        return r.json()
    except ValueError:
        raise RuntimeError(f"{path} returned non-JSON: {r.text[:200]}")


def challonge_get_all(path: str, creds: Credentials,
                      params: Optional[dict] = None) -> list:
    """Every page of a collection endpoint, as a flat list of resources.

    Challonge paginates with ``page``/``per_page`` and does not reliably report
    a total, so the loop ends on the first short page. The page cap is a
    guard against an endpoint that ignores ``page`` and keeps returning the
    first one -- without it that is an infinite loop rather than an error.
    """
    out: list = []
    for page in range(1, 101):
        query = dict(params or {})
        query.update({"page": page, "per_page": PAGE_SIZE})
        payload = challonge_get(path, creds, query)
        rows = payload.get("data")
        if not isinstance(rows, list):
            # A single-resource response reached a collection call.
            return [rows] if rows else out
        out.extend(rows)
        if len(rows) < PAGE_SIZE:
            break
    return out


def attrs(obj) -> dict:
    """The attribute bag of a JSON:API resource, tolerating the flat v1 shape."""
    if not isinstance(obj, dict):
        return {}
    inner = obj.get("attributes")
    return inner if isinstance(inner, dict) else obj


def match_player_ids(match) -> tuple:
    """``(player1_id, player2_id)`` for a match, as strings, either may be "".

    v2.1 gives a match **no** player relationship: its ``relationships`` bag
    holds only ``attachments``, and there is no ``player1``/``player2`` there
    or on the attributes. The two participants appear instead as
    ``points_by_participant``, whose order is the real slot order -- the
    ``scores`` string ("1 - 2") reads against it in the same order, and it is
    not winner-first. So it is read as player1, player2.

    ``rel_id`` is still tried first: it is what the documented v1 shape uses,
    and a response carrying either shape then works.
    """
    p1, p2 = rel_id(match, "player1"), rel_id(match, "player2")
    if p1 and p2:
        return p1, p2
    points = attrs(match).get("points_by_participant")
    if isinstance(points, list) and len(points) >= 2:
        ids = [str(e.get("participant_id")) for e in points[:2]
               if isinstance(e, dict) and e.get("participant_id") is not None]
        if len(ids) == 2:
            return ids[0], ids[1]
    return p1, p2


def rel_id(obj, name: str) -> str:
    """The id of a to-one relationship, as a string, or "".

    Looks in ``relationships[name].data.id`` first, then at a flat
    ``{name}_id`` on the attributes and on the object itself -- the v1 shape,
    and the shape some v2.1 responses still use for ``winner``/``loser``.
    """
    if not isinstance(obj, dict):
        return ""
    rels = obj.get("relationships")
    if isinstance(rels, dict):
        entry = rels.get(name)
        if isinstance(entry, dict):
            data = entry.get("data")
            if isinstance(data, dict) and data.get("id") is not None:
                return str(data["id"])
    for bag in (attrs(obj), obj):
        value = bag.get(f"{name}_id")
        if value is not None and value != "":
            return str(value)
    return ""


def resource_id(obj) -> str:
    """The id of a resource, as a string."""
    if not isinstance(obj, dict):
        return ""
    value = obj.get("id")
    if value is None:
        value = attrs(obj).get("id")
    return "" if value is None else str(value)


def get_tournament(slug: str, creds: Credentials) -> dict:
    """The tournament resource for a slug (or a pasted tournament URL)."""
    slug = normalize_slug(slug)
    if not slug:
        raise RuntimeError("No tournament slug given.")
    payload = challonge_get(f"tournaments/{slug}.json", creds)
    data = payload.get("data")
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict):
        raise RuntimeError(f"No tournament found for slug: {slug!r}")
    return data


def get_participants(tournament_id: str, creds: Credentials) -> list:
    return challonge_get_all(f"tournaments/{tournament_id}/participants.json",
                             creds)


def get_matches(tournament_id: str, creds: Credentials) -> list:
    return challonge_get_all(f"tournaments/{tournament_id}/matches.json",
                             creds)


def participant_name(obj) -> str:
    """A participant's display name.

    ``name`` is what a TO typed; ``username`` is the Challonge account, present
    when the entrant registered rather than being added by hand.
    """
    bag = attrs(obj)
    for key in ("name", "display_name", "username", "challonge_username"):
        value = (bag.get(key) or "").strip() if isinstance(bag.get(key), str) else ""
        if value:
            return value
    return ""


def strip_sponsor(name: str) -> str:
    """``"NG | Azul"`` -> ``"Azul"``, matching the other fetchers."""
    if " | " in name:
        return name.split(" | ", 1)[1]
    return name


def warn(message: str) -> None:
    print(message, file=sys.stderr)


def _check_auth(props_path: str = PROPS_FILE, slug: str = "") -> int:
    """Report whether the configured credentials actually authorize.

    Worth having as its own entry point: "the fetch produced nothing" has
    several causes, and this separates "the credentials are wrong" from them
    before any slug is involved. With a slug it also answers the question the
    docs are vague about -- whether a client-credentials token can see a
    tournament that was created on the website rather than through the app.
    """
    creds = load_credentials(props_path)
    print(f"app.properties: {props_path}")
    if not creds:
        print("FAIL: no credentials configured.\n")
        print(missing_credentials_message(props_path))
        return 1
    print(f"Credentials:    {creds.kind}"
          + (f" (client id {creds.client_id[:8]}...)" if creds.client_id and
             not creds.api_key else ""))
    if not creds.api_key:
        try:
            creds.token()
        except (RuntimeError, requests.RequestException) as exc:
            print(f"FAIL: could not get an access token.\n\n{exc}")
            return 1
        print(f"Access token:   OK, granted scope: "
              f"{creds.scope or '(none reported)'}")

    target = normalize_slug(slug) if slug else ""
    if not target:
        print("\nCredentials look usable. Pass a tournament slug or URL to "
              "check that this account can actually read it, e.g.\n"
              "  py -3.12 challonge_api.py challonge.com/my-weekly-42")
        return 0
    print(f"\nReading tournament: {target}")
    try:
        tournament = get_tournament(target, creds)
    except (RuntimeError, requests.RequestException) as exc:
        print(f"FAIL: {exc}")
        return 1
    bag = attrs(tournament)
    print(f"OK: {bag.get('name')!r}  |  type {bag.get('tournament_type')}  |  "
          f"state {bag.get('state')}  |  "
          f"{bag.get('participants_count')} participants")
    return 0


if __name__ == "__main__":
    sys.exit(_check_auth(slug=sys.argv[1] if len(sys.argv) > 1 else ""))
