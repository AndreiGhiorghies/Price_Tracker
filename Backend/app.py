from flask import Flask, render_template, request

app = Flask(__name__,static_folder="../Frontend", template_folder="../Frontend/HTML")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/product.html")
def product():
    product_id = request.args.get("product_id")
    
    if product_id is not None:
        product_id = int(product_id)

    return render_template("product.html", product_id=product_id)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
