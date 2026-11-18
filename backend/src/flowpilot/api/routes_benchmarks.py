"""Benchmark execution and evaluation history routes (Baseline A vs Baseline B)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from flowpilot.api.deps import CurrentUserDep, SessionDep
from flowpilot.benchmarks.dataset import build_benchmark_suite
from flowpilot.benchmarks.runner import run_comparative_benchmark
from flowpilot.db.models import EvaluationRun
from flowpilot.schemas.benchmarks import (
    BenchmarkComparisonOut,
    BenchmarkRunRequest,
    EvaluationRunOut,
)

router = APIRouter(prefix="/api/v1/benchmarks", tags=["benchmarks"])


@router.post("/run", response_model=BenchmarkComparisonOut)
async def execute_benchmark(
    payload: BenchmarkRunRequest,
    _user: CurrentUserDep,
    session: SessionDep,
) -> BenchmarkComparisonOut:
    cases = build_benchmark_suite(include_stress_cases=payload.include_stress_cases)
    result = await run_comparative_benchmark(
        cases=cases,
        dataset_name=payload.dataset_name,
        run_name=payload.name,
        session=session,
    )
    return BenchmarkComparisonOut(
        baseline_monolithic=EvaluationRunOut.model_validate(result["baseline_row"]),
        flowpilot_orchestrator=EvaluationRunOut.model_validate(result["flowpilot_row"]),
        token_reduction_pct=result["token_reduction_pct"],
        cost_reduction_pct=result["cost_reduction_pct"],
        p95_latency_reduction_pct=result["p95_latency_reduction_pct"],
        throughput_multiplier=result["throughput_multiplier"],
        f1_delta=result["f1_delta"],
        calibration_bins=result["calibration_bins"],
        report_markdown=result["report_markdown"],
    )


@router.get("/runs", response_model=list[EvaluationRunOut])
async def list_evaluation_runs(
    _user: CurrentUserDep, session: SessionDep
) -> list[EvaluationRunOut]:
    rows = list(
        (
            await session.execute(
                select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(30)
            )
        )
        .scalars()
        .all()
    )
    return [EvaluationRunOut.model_validate(r) for r in rows]


@router.get("/latest-comparison", response_model=BenchmarkComparisonOut)
async def latest_comparison(_user: CurrentUserDep, session: SessionDep) -> BenchmarkComparisonOut:
    base_res = await session.execute(
        select(EvaluationRun)
        .where(EvaluationRun.mode == "baseline_monolithic")
        .order_by(EvaluationRun.created_at.desc())
        .limit(1)
    )
    fp_res = await session.execute(
        select(EvaluationRun)
        .where(EvaluationRun.mode == "flowpilot_orchestrator")
        .order_by(EvaluationRun.created_at.desc())
        .limit(1)
    )
    base = base_res.scalar_one_or_none()
    fp = fp_res.scalar_one_or_none()
    if base is None or fp is None:
        raise HTTPException(
            status_code=404, detail="No benchmark runs found yet. Trigger /run first."
        )

    token_red = round((1.0 - fp.avg_tokens / max(base.avg_tokens, 1.0)) * 100.0, 2)
    cost_red = round((1.0 - fp.avg_cost_usd / max(base.avg_cost_usd, 1e-9)) * 100.0, 2)
    p95_red = round((1.0 - fp.p95_latency_ms / max(base.p95_latency_ms, 1.0)) * 100.0, 2)
    tput_mult = round(fp.throughput_rps / max(base.throughput_rps, 0.01), 2)
    f1_delta = round(fp.field_f1 - base.field_f1, 4)

    return BenchmarkComparisonOut(
        baseline_monolithic=EvaluationRunOut.model_validate(base),
        flowpilot_orchestrator=EvaluationRunOut.model_validate(fp),
        token_reduction_pct=token_red,
        cost_reduction_pct=cost_red,
        p95_latency_reduction_pct=p95_red,
        throughput_multiplier=tput_mult,
        f1_delta=f1_delta,
        calibration_bins=list((fp.details_json or {}).get("calibration_bins") or []),
    )
