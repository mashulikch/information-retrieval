
# Homework 1, read this first

  

You are building a small crawler. To make that possible without pointing 300  laptops at some poor website, the homework ships with its own website. It runs  on your machine, it has no connection to the internet, and it is full of the things that make crawling annoying in real life: redirects, a redirect loop,  pages that answer 404 and 500, a robots.txt that has an opinion about your bot, hidden text, a shop that keeps its products behind an API, and a second host that asks you to slow down.

  

## What you need

  

Python 3.10 or newer, plus two libraries.

  

```

python -m pip install -r requirements.txt

```

  

That is it. No `lxml`, no `nltk`, no Selenium. If you install them anyway they  will not be there when we grade, and code that needs them scores zero on that  task.

  

On Windows, if `python` opens the Microsoft Store or complains, use `py -3`  everywhere instead:

```

py -3 -m pip install -r requirements.txt

```

  

## Getting started

  

Put `Homework01.ipynb`, `ir_sandbox.py` and `requirements.txt` in the same  folder. Open the notebook, run the first cell, and you should see something like  

```

Practice site is running (ir_sandbox 2026.1).  
museum site http://127.0.0.1:8765/
partner site http://127.0.0.1:8766/

```

  

Click the museum address. A real page opens in your browser. Look around it,  read its source, and keep that tab open while you work because it can make the tasks much  easier to picture.

  

I advise you on two things:

- Build every address with `SITE.url("/about/")` and never type a port number into  your code.

-  `SITE.requests()` shows every request the site received. When your crawler  does something strange, this is the fastest way to find out what it actually asked for.

  

## When something goes wrong

  

The port numbers are different from my friend's. That is fine. If 8765 is  already busy on your machine, the site quietly takes a free port and prints it.  Nothing else changes, as long as you use `SITE.url(...)`.

  
`ModuleNotFoundError: requests`. The libraries went into a different Python than  the one your notebook runs. Run `import sys; print(sys.executable)` in the  notebook and install with that exact path, or use `py -3 -m pip install ...`

  

Everything times out and nothing works. If you are on a VPN or a corporate  proxy, turn it off and restart the kernel. The sandbox already tells requests to  skip the proxy for local addresses, but some setups are stubborn.

  

`FeatureNotFound` from BeautifulSoup. You asked for a parser we do not have. Use  `BeautifulSoup(html, "html.parser")`.

  
`check_notebook` says there is no such file. Save the notebook first, and pass  the name exactly as it appears on disk, including the `.ipynb`.

  

Anything else, you can ask


  

## How you are graded

  

Rename the notebook to your university email plus `.ipynb`, for example:

`i.ivanov@innopolis.university.ipynb`. A wrong name means zero, and yes, we mean  it, because the grading script finds you by that name.

  

We import your notebook and call your functions. Only imports, function  definitions, class definitions and simple constants survive that import.

Anything you run at the top level of a cell is ignored, so never build something  important there and expect us to see it.

  

`ir_sandbox.check(1, globals())` runs the tests for one task while you work. The  last cell of the notebook grades the saved file exactly the way we do. Use it before you upload and it takes ten seconds only

  

Keep in mind: we grade on another copy of the same site. Same kinds  of pages, same rules, different addresses, different texts, different products. So a solution that reads the task passes both, and a solution that memorises the pages in front of you passes only the first one.

  

Partial credit is also considered. If your task  handles the normal case and fails the  strange one, it is far better than an empty cell.

  

## The interview

  

After the deadline you sit with a TA for a few minutes and talk about your own code. This is not an exam and there is nothing to revise. We open your file, we point at a function, and we ask things like: why does this return None here, what happens if the server sends a 500, walk me through the queue after the  first page, what would you change to make this stop after ten pages, etc, so you can expect everything to test your understanding of the assignment.

  

How to be ready: read your own submission once before you come, and make sure there is no line in it that you cannot explain. 
  
You may use AI tools while writing this homework. We are not going to pretend  otherwise and we are not hunting for it. The rule is simple: you own what you submit. If you cannot explain a line of it, you will lose points.

Coming to the interview is required. The schedule and how the interview affects the final number are announced later.

  

## Submitting

Upload the notebook to Moodle. One file, nothing else. Do not upload  `ir_sandbox.py`, and do not change it, we use our own copy.
