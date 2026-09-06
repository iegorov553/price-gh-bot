window.BENCHMARK_DATA = {
  "lastUpdate": 1788697124527,
  "repoUrl": "https://github.com/iegorov553/price-gh-bot",
  "entries": {
    "Benchmark": [
      {
        "commit": {
          "author": {
            "email": "iegorov553@gmail.com",
            "name": "Ivan Egorov",
            "username": "iegorov553"
          },
          "committer": {
            "email": "iegorov553@gmail.com",
            "name": "Ivan Egorov",
            "username": "iegorov553"
          },
          "distinct": true,
          "id": "edc01d5ae6ca0158a8612bcbdb7bc011c91a63ca",
          "message": "ci: add write permissions and fallback for benchmark action",
          "timestamp": "2026-08-15T17:54:17+02:00",
          "tree_id": "2377f1796db809d71d37e11879b730bdeadf1f97",
          "url": "https://github.com/iegorov553/price-gh-bot/commit/edc01d5ae6ca0158a8612bcbdb7bc011c91a63ca"
        },
        "date": 1786809474492,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests_new/benchmarks/test_pricing_benchmark.py::test_benchmark_shipping_estimation",
            "value": 34464.39953953504,
            "unit": "iter/sec",
            "range": "stddev: 0.0000021159739500854354",
            "extra": "mean: 29.015448212085435 usec\nrounds: 1622"
          },
          {
            "name": "tests_new/benchmarks/test_pricing_benchmark.py::test_benchmark_grailed_html_classification",
            "value": 477222.5758946028,
            "unit": "iter/sec",
            "range": "stddev: 4.7306271714157355e-7",
            "extra": "mean: 2.09545828406252 usec\nrounds: 83697"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "iegorov553@gmail.com",
            "name": "Ivan Egorov",
            "username": "iegorov553"
          },
          "committer": {
            "email": "iegorov553@gmail.com",
            "name": "Ivan Egorov",
            "username": "iegorov553"
          },
          "distinct": false,
          "id": "4d30896a943c3233a8a8552203afec7a4d73b6fc",
          "message": "Merge branch 'dev' into staging",
          "timestamp": "2026-09-06T00:45:12+02:00",
          "tree_id": "cfbf461ca797afddff3bf4ec1bb454965056e65e",
          "url": "https://github.com/iegorov553/price-gh-bot/commit/4d30896a943c3233a8a8552203afec7a4d73b6fc"
        },
        "date": 1788697123992,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests_new/benchmarks/test_pricing_benchmark.py::test_benchmark_shipping_estimation",
            "value": 33880.89274055065,
            "unit": "iter/sec",
            "range": "stddev: 0.0000026613185932694635",
            "extra": "mean: 29.515160880136467 usec\nrounds: 2045"
          },
          {
            "name": "tests_new/benchmarks/test_pricing_benchmark.py::test_benchmark_grailed_html_classification",
            "value": 487359.29753153113,
            "unit": "iter/sec",
            "range": "stddev: 4.6193801719636444e-7",
            "extra": "mean: 2.0518742641517003 usec\nrounds: 85274"
          }
        ]
      }
    ]
  }
}