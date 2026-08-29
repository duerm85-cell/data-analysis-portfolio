"""PySpark 版行情清洗与因子批处理流水线。

该实现与 Pandas 流水线并存，用于展示可横向扩展的数据处理设计。
"""

import argparse
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _P(*parts):
    return os.path.join(_BASE_DIR, *parts)


def build_spark_session(app_name="quant-data-pipeline"):
    try:
        from pyspark.sql import SparkSession
    except ImportError as exc:
        raise RuntimeError(
            "未安装 PySpark，请运行 pip install -r requirements-spark.txt"
        ) from exc

    return (
        SparkSession.builder.appName(app_name)
        .config("spark.sql.session.timeZone", "Asia/Shanghai")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )


def transform_market_data(spark, input_path):
    """读取清洗层 CSV，执行质量过滤、去重和窗口因子计算。"""
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    source = (
        spark.read.option("header", True)
        .option("inferSchema", True)
        .csv(os.path.join(input_path, "*_daily.csv"))
        .withColumn("source_file", F.input_file_name())
        .withColumn(
            "code",
            F.regexp_extract("source_file", r"[\\/](\d{6})_daily\.csv$", 1),
        )
        .withColumn("date", F.to_date("date"))
    )

    required = ["code", "date", "open", "high", "low", "close", "volume", "amount"]
    missing = [column for column in required if column not in source.columns]
    if missing:
        raise ValueError(f"清洗层缺少字段: {missing}")

    valid_condition = F.coalesce((
        F.col("code").rlike(r"^\d{6}$")
        & F.col("date").isNotNull()
        & (F.col("close") > 0)
        & (F.col("volume") >= 0)
        & (F.col("high") >= F.greatest(F.col("open"), F.col("close")))
        & (F.col("low") <= F.least(F.col("open"), F.col("close")))
    ), F.lit(False))

    quality_summary = source.agg(
        F.count("*").alias("input_rows"),
        F.sum(F.when(valid_condition, 1).otherwise(0)).alias("valid_rows"),
        F.sum(F.when(~valid_condition, 1).otherwise(0)).alias("invalid_rows"),
        F.countDistinct("code").alias("stock_count"),
        F.min("date").alias("start_date"),
        F.max("date").alias("end_date"),
    )

    clean = source.filter(valid_condition).dropDuplicates(["code", "date"])
    history = Window.partitionBy("code").orderBy("date")
    last_5 = history.rowsBetween(-4, 0)
    last_20 = history.rowsBetween(-19, 0)

    factors = (
        clean.withColumn("ret", F.col("close") / F.lag("close").over(history) - 1)
        .withColumn("ma5", F.avg("close").over(last_5))
        .withColumn("ma20", F.avg("close").over(last_20))
        .withColumn("volatility_20d", F.stddev_samp("ret").over(last_20))
        .withColumn("volume_ma5", F.avg("volume").over(last_5))
        .withColumn("volume_ratio", F.col("volume") / (F.col("volume_ma5") + F.lit(1.0)))
        .withColumn("label", F.lead("ret", 1).over(history))
        .withColumn("year", F.year("date"))
        .drop("source_file")
    )
    return factors, quality_summary


def run_pipeline(input_path, output_path, mode="overwrite"):
    spark = build_spark_session()
    try:
        factors, quality_summary = transform_market_data(spark, input_path)
        factors.write.mode(mode).partitionBy("year").parquet(
            os.path.join(output_path, "factors")
        )
        quality_summary.coalesce(1).write.mode("overwrite").json(
            os.path.join(output_path, "quality_report")
        )
        factors.createOrReplaceTempView("market_factors")
        spark.sql(
            """
            SELECT year, COUNT(*) AS row_count, COUNT(DISTINCT code) AS stock_count
            FROM market_factors
            GROUP BY year
            ORDER BY year
            """
        ).show(truncate=False)
    finally:
        spark.stop()


def main():
    parser = argparse.ArgumentParser(description="PySpark 量化数据批处理流水线")
    parser.add_argument("--input", default=_P("data", "clean"))
    parser.add_argument("--output", default=_P("data", "spark_processed"))
    parser.add_argument("--mode", choices=["overwrite", "append"], default="overwrite")
    args = parser.parse_args()
    run_pipeline(args.input, args.output, mode=args.mode)


if __name__ == "__main__":
    main()
