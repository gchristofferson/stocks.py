import datetime
import os

from cs50 import SQL, eprint
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions
from werkzeug.security import check_password_hash, generate_password_hash
from passlib.context import CryptContext

from helpers import apology, message, login_required, lookup, usd

# Ensure environment variable is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # retrieve users stocks from database
    user_id = session["user_id"]
    username = session["username"]

    # retrieve the users current cash balance
    cash = session["cash"]

    # if we haven't set the balance, set it equal to cash
    if session["balance"] == "":
        balance = cash

    else:
        balance = session["balance"]

    # if we haven't already retrieve current pricing for each stock
    if session["stocks"] == "":
        stocks = db.execute("SELECT *, SUM(shares) FROM purchases WHERE username = :username GROUP BY stock", username=username)
        session["stocks"] = stocks
        index = 0
        for i in session["stocks"]:
            stock = i["stock"]
            while True:
                try:
                    price = lookup(stock)
                    price = round(price["price"], 2)
                except TypeError:
                    continue
                break

            # retrieve the total number of shares for each stock
            sumShares = session["stocks"][index]["SUM(shares)"]

            # calculate the value of each holding (shares times price)
            total = round(price * sumShares, 2)
            balance = round(balance + total, 2)
            session["stocks"][index]["currentPrice"] = "{:.2f}".format(price)
            session["stocks"][index]["total"] = "{:.2f}".format(total)
            index += 1
        session["balance"] = balance

    return render_template("index.html", stocks=session["stocks"], cash="{:.2f}".format(session["cash"]), balance="{:.2f}".format(session["balance"]))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    user_id = session["user_id"]

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # validate users stock and shares selection
        symbol = request.form.get("symbol")
        quote = lookup(symbol)
        shares = request.form.get("shares")

        # check if stock is valid
        if not quote and shares.isdigit():
            return apology("not a valid stock")

        if shares.isdigit():
            shares = float(shares)
            if shares > 0:
                # select how much cash the user currently has in users
                cash = session["cash"]

                # calculate price to purchase selected number of shares
                session["price"] = quote["price"] * shares
                price = session["price"]
                balance = cash - price

                # Render an apology if the user cannot afford the number of shares at the current price
                if balance < 0:
                    return apology("sorry, you can't afford the number of shares at the current price")

                # otherwise add the users' purchase to the purchases db table
                else:
                    username = session["username"]
                    timestamp = datetime.datetime.now()
                    db.execute("INSERT INTO purchases (username, stock, shares, price, timestamp) VALUES(:username, :stock, :shares, :price, :timestamp)",
                               username=username, stock=symbol, shares=shares, price=price, timestamp=timestamp)

                    # update users cash balance
                    db.execute("UPDATE users SET cash = :balance WHERE id = :user", balance=balance, user=user_id)

                # clear session stocks and refresh balance
                session["stocks"] = ""
                balance = db.execute("SELECT cash FROM users WHERE username = :username", username=username)
                balance = balance[0]["cash"]
                session["balance"] = balance
                session["cash"] = balance
                return redirect("/")

            # user didn't enter a positive number greater than 0
            else:
                return apology("number of shares must be greater than 0")

        # user didn't enter a valid value for number of shares
        else:
            return apology("not a valid entry")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    username = session["username"]

    # retrieve user transactions history
    transactions = db.execute("SELECT * FROM purchases WHERE username = :username", username=username)
    session["transactions"] = transactions

    return render_template("history.html", transactions=session["transactions"])


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password")

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]
        user_id = session["user_id"]

        # initialize session stocks and balance
        session["stocks"] = ""
        session["balance"] = ""

        # Remember username of user
        username = db.execute("SELECT username FROM users WHERE id = :user_id", user_id=user_id)
        username = username[0]["username"]
        session["username"] = username

        # retrieve the users current cash balance
        cash = db.execute("SELECT cash FROM users WHERE :username = username", username=username)
        cash = round(cash[0]["cash"], 2)
        balance = cash
        session["cash"] = cash

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Retrieve the quote for the stock
        symbol = request.form.get("symbol")
        quote = lookup(symbol)

        # check if stock is valid
        if not quote:
            return apology("not a valid stock")

        # if valid, display current price for stock
        else:
            session["symbol"] = quote["symbol"]
            session["price"] = '{:.2f}'.format(quote["price"])
            return redirect("/quoted")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/quoted")
@login_required
def quoted():
    """Display stock quote."""
    return render_template("quoted.html", symbol=session["symbol"], price=session["price"])


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        msg = ""
        # Ensure username was submitted
        if not request.form.get("username"):
            msg = "must provide username"

        # Ensure password was submitted
        elif not request.form.get("password"):
            msg = "must provide password"

        # Ensure passwords match
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        if password != confirmation:
            msg = "passwords don't match"

        if msg != "":
            return apology(msg)

        # All is valid. Encrypt password
        else:
            secret = generate_password_hash(password)

            # Ensure username is unique
            result = db.execute("SELECT * FROM users WHERE username = :username",
                                username=request.form.get("username"))
            if len(result) == 1:
                return apology("username already exists")

            # Add user to database
            username = request.form.get("username")
            db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)", username=username, hash=secret)

            # Log user in automatically. Store their id in session
            user = db.execute("SELECT * FROM users WHERE username = :username",
                              username=request.form.get("username"))
            session["user_id"] = user[0]["id"]
            session["username"] = username

            # initialize session stocks and balance
            session["stocks"] = ""
            session["balance"] = ""

            # retrieve the users current cash balance
            cash = db.execute("SELECT cash FROM users WHERE :username = username", username=username)
            cash = round(cash[0]["cash"], 2)
            balance = cash
            session["cash"] = cash

            # Redirect user to home page
            return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    """User Settings"""

    username = session["username"]

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        current = request.form.get("current")
        password = request.form.get("password")

        msg = ""
        # Ensure username was submitted
        if not current:
            msg = "must provide current password"

        # Ensure password was submitted
        elif not password:
            msg = "must provide new password"

        # Ensure current password is valid
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=username)
        if not check_password_hash(rows[0]["hash"], current):
            msg = "the current password you entered is not valid"

        # Ensure passwords match
        confirmation = request.form.get("confirmation")
        if password != confirmation:
            msg = "passwords don't match"

        if msg != "":
            return apology(msg)

        # All is valid. Encrypt new password
        else:
            secret = generate_password_hash(password)

            # update users password
            db.execute("UPDATE users SET hash = :secret WHERE username = :username", secret=secret, username=username)

            # Redirect user to home page
            return message("password successfully updated")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("settings.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    user_id = session["user_id"]
    username = session["username"]

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # validate users stock and shares selection
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("no stock was selected from the menu")
        while True:
            try:
                quote = lookup(symbol)
            except quote == None:
                continue
            break
        shares = request.form.get("shares")
        holdings = db.execute(
            "SELECT *, SUM(shares) FROM purchases WHERE username = :username AND stock = :stock GROUP BY stock", username=username, stock=symbol)
        holdings = holdings[0]["SUM(shares)"]

        # check if stock is valid
        if not quote and shares.isdigit():
            return apology("not a valid stock")

        if shares.isdigit():

            # check if user owns the number of shares
            holdings = float(holdings)
            shares = float(shares)
            negShares = -shares
            if shares > holdings:
                return apology("sorry, you don't own that many shares of this stock")

            if shares > 0:
                # select how much cash the user currently has in users
                cash = session["cash"]

                # calculate sell price for selected number of shares
                session["price"] = quote["price"] * shares
                price = session["price"]

                # remove selected shares of stock from users portfolio
                shares = holdings - shares

                # log sale as a negative quantity to update shares
                shares = negShares
                timestamp = datetime.datetime.now()
                db.execute("INSERT INTO purchases (username, stock, shares, price, timestamp) VALUES(:username, :stock, :shares, :price, :timestamp)",
                           username=username, stock=symbol, shares=shares, price=price * -1, timestamp=timestamp)

                # update userscash balance
                balance = cash + price
                db.execute("UPDATE users SET cash = :balance WHERE id = :user", balance=balance, user=user_id)

                # clear session stocks and balance
                session["stocks"] = ""
                session["balance"] = ""
                cash = db.execute("SELECT cash FROM users WHERE :username = username", username=username)
                cash = round(cash[0]["cash"], 2)
                session["cash"] = cash
                return redirect("/")

            # user didn't enter a positive number greater than 0
            else:
                return apology("number of shares must be greater than 0")

        # user didn't enter a valid value for number of shares
        else:
            return apology("not a valid entry")

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # retrieve stocks, current prices, and number of shares from session
        return render_template("sell.html", stocks=session["stocks"])


def errorhandler(e):
    """Handle error"""
    return apology(e.name, e.code)


# listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
