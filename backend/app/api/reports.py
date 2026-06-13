from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import Experiment
from app.schemas.schemas import ComparisonRequest
from app.services.report import generate_comparison_report

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("/comparison")
async def create_comparison_report(data: ComparisonRequest, db: AsyncSession = Depends(get_db)):
    report = await generate_comparison_report(data.experiment_ids)
    return report


@router.post("/export-pdf")
async def export_pdf_report(data: ComparisonRequest, db: AsyncSession = Depends(get_db)):
    report = await generate_comparison_report(data.experiment_ids)

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        import io

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph("MARL Experiment Comparison Report", styles["Title"]))
        elements.append(Spacer(1, 20))

        exp_data = [["Name", "Algorithm", "Avg Reward", "Success Rate", "Convergence Ep"]]
        for p in report.get("performance", []):
            exp_data.append([
                str(p.get("name", "")),
                str(p.get("algorithm", "")),
                f"{p.get('avg_reward', 0):.2f}",
                f"{p.get('success_rate', 0):.2%}",
                str(p.get("convergence_ep", 0)),
            ])

        table = Table(exp_data)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 20))

        elements.append(Paragraph("Statistical Significance", styles["Heading2"]))
        sig_data = [["Exp A", "Exp B", "p-value", "Significant"]]
        for s in report.get("significance", []):
            sig_data.append([
                str(s.get("exp_a", "")),
                str(s.get("exp_b", "")),
                f"{s.get('p_value', 'N/A')}" if s.get("p_value") is not None else "N/A",
                "Yes" if s.get("significant") else "No",
            ])
        sig_table = Table(sig_data)
        sig_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(sig_table)

        doc.build(elements)
        buffer.seek(0)

        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=marl_comparison_report.pdf"},
        )
    except ImportError:
        return {"report": report, "pdf_export": "reportlab not available"}
