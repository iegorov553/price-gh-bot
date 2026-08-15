window.BENCHMARK_DATA = {
  "lastUpdate": 1786809474984,
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
      }
    ]
  }
}