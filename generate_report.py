from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, ListFlowable, ListItem, Image
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame
from sqlalchemy import create_engine, text
import os
import pandas as pd
from dotenv import load_dotenv
from reportlab.lib.utils import ImageReader

# Color: Darker blue (0, 51, 153)
DARK_BLUE = colors.Color(0/255, 51/255, 153/255)

load_dotenv()
db_uri = os.getenv("DB_URI")
engine = create_engine(db_uri)

# Get the absolute path to the project root directory
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PSU_LOGO_PATH = os.path.join(PROJECT_ROOT, "frontend", "Public", "Images", "Prince Sultan Univeristy.png")

# Custom Page Template to add logo
class LogoDocTemplate(BaseDocTemplate):
    def __init__(self, filename, **kwargs):
        super().__init__(filename, **kwargs)
        header_height = 30 * mm  # Height for header (logo)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height - header_height, id='normal', topPadding=0)
        template = PageTemplate(id='logo', frames=frame, onPage=self.add_logo)
        self.addPageTemplates([template])
        self.header_height = header_height

    def add_logo(self, canvas, doc):
        try:
            # Draw logo (right)
            logo_path = PSU_LOGO_PATH
            logo_width = 28  # mm
            logo_height = 22  # mm
            x_logo = doc.pagesize[0] - doc.rightMargin - logo_width * mm
            y_logo = doc.pagesize[1] - logo_height * mm - 18
            if os.path.exists(logo_path):
                canvas.drawImage(logo_path, x_logo, y_logo, width=logo_width*mm, height=logo_height*mm, preserveAspectRatio=True, mask='auto')
        except Exception as e:
            print(f"Header error: {e}")

def safe_text(text):
    text = str(text).replace('–', '-').replace('—', '-')
    return text.encode('latin-1', 'ignore').decode('latin-1')

def generate_student_report_reportlab(student_id):
    # Use absolute path for PDF output
    output_path = os.path.join(PROJECT_ROOT, f"student_{student_id}_report.pdf")
    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    elements = []
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='BigTitle', fontName='Times-Bold', fontSize=22, textColor=DARK_BLUE, alignment=TA_CENTER, spaceAfter=16))
    styles.add(ParagraphStyle(name='Heading', fontName='Times-Bold', fontSize=15, textColor=DARK_BLUE, spaceAfter=8))
    styles.add(ParagraphStyle(name='SubHeading', fontName='Times-Bold', fontSize=13, textColor=DARK_BLUE, spaceAfter=6))
    styles.add(ParagraphStyle(name='Body', fontName='Times-Roman', fontSize=12, spaceAfter=4))
    styles.add(ParagraphStyle(name='BoldBody', fontName='Times-Bold', fontSize=12, spaceAfter=4))
    styles.add(ParagraphStyle(name='TableCell', fontName='Times-Roman', fontSize=12, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='TableHeader', fontName='Times-Bold', fontSize=12, alignment=TA_CENTER, textColor=DARK_BLUE))

    # Update styles for increased line spacing
    styles['BigTitle'].leading = 28
    styles['Heading'].leading = 20
    styles['SubHeading'].leading = 18
    styles['Body'].leading = 16
    styles['BoldBody'].leading = 16
    styles['TableCell'].leading = 15
    styles['TableHeader'].leading = 15

    # Add the logo as a normal image at the top (preserve aspect ratio)
    logo_path = PSU_LOGO_PATH
    if os.path.exists(logo_path):
        logo_width = 80  # in points (about 28mm)
        img = ImageReader(logo_path)
        iw, ih = img.getSize()
        aspect = ih / float(iw)
        logo_height = logo_width * aspect
        elements.append(Image(logo_path, width=logo_width, height=logo_height, hAlign='RIGHT'))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph("Student Academic Report", styles['BigTitle']))
    elements.append(Spacer(1, 8))

    # Student Info
    student_query = text("""
        SELECT s.*, d.department_name, m.major_name,
            a.Fname AS advisor_fname, a.Lname AS advisor_lname, a.email AS advisor_email
        FROM Student s
        JOIN Department d ON s.department_id = d.department_id
        JOIN Major m ON s.major_id = m.major_id
        LEFT JOIN Advisor a ON s.advisor_id = a.advisor_id
        WHERE s.student_id = :student_id
    """)
    student = pd.read_sql(student_query, engine, params={"student_id": student_id}).iloc[0]
    elements.append(Paragraph("1. Student Information", styles['Heading']))
    info_list = [
        ("Full Name", f"{student['Fname']} {student['Lname']}"),
        ("Student ID", student['student_id']),
        ("Email", student['email']),
        ("Department and Major", f"{student['department_name']} - {student['major_name']}"),
        ("Advisor", f"{student['advisor_fname']} {student['advisor_lname']} ({student['advisor_email']})"),
        ("Enrollment Year", student['enrollment_year']),
        ("Completed Hours", student['completed_hours']),
        ("Current GPA", student['current_gpa']),
        ("Cumulative GPA", student['cumulative_gpa']),
        ("Warning Notes", student['Warnings'] or "None")
    ]
    for label, value in info_list:
        elements.append(Paragraph(f'<b>{safe_text(label)}:</b> {safe_text(value)}', styles['Body']))
    elements.append(Spacer(1, 8))

    # GPA History
    elements.append(Paragraph("2. Academic Performance History", styles['Heading']))
    gpa_query = text("SELECT semester, gpa FROM Student_GPA_History WHERE student_id = :student_id")
    gpa_df = pd.read_sql(gpa_query, engine, params={"student_id": student_id})
    if not gpa_df.empty:
        gpa_data = [[Paragraph("Semester", styles['TableHeader']), Paragraph("GPA", styles['TableHeader'])]] + [
            [Paragraph(safe_text(row[0]), styles['TableCell']), Paragraph(safe_text(row[1]), styles['TableCell'])] for row in gpa_df.values.tolist()
        ]
        t = Table(gpa_data, colWidths=[70*mm, 30*mm])
        t.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('BACKGROUND', (0,0), (-1,0), colors.whitesmoke)
        ]))
        elements.append(t)
        elements.append(Spacer(1, 8))

    # Course Enrollments
    def fetch_courses(status):
        query = f"""
        SELECT e.course_id, c.course_name, e.semester, e.grade,
               COALESCE(a.absence_count, 0) AS absences
        FROM Student_Course_Enrollment e
        JOIN Course c ON c.course_id = e.course_id
        LEFT JOIN Student_Course_Absence a 
            ON e.student_id = a.student_id AND e.course_id = a.course_id AND e.semester = a.semester
        WHERE e.status = :status AND e.student_id = :student_id
        """
        return pd.read_sql(text(query), engine, params={"student_id": student_id, "status": status})

    elements.append(Paragraph("3. Course Enrollments", styles['Heading']))
    # 3a
    elements.append(Paragraph("3a. Current Courses", styles['SubHeading']))
    current_df = fetch_courses("Current")
    if not current_df.empty:
        data = [[Paragraph(h, styles['TableHeader']) for h in ["ID", "Name", "Semester", "Grade", "Absences"]]] + [
            [Paragraph(safe_text(str(row["course_id"])), styles['TableCell']),
             Paragraph(safe_text(str(row["course_name"])), styles['TableCell']),
             Paragraph(safe_text(str(row["semester"])), styles['TableCell']),
             Paragraph(safe_text(str(row["grade"])), styles['TableCell']),
             Paragraph(safe_text(str(row["absences"])), styles['TableCell'])] for _, row in current_df.iterrows()
        ]
        t = Table(data, colWidths=[25*mm, 60*mm, 30*mm, 20*mm, 20*mm])
        t.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('BACKGROUND', (0,0), (-1,0), colors.whitesmoke)
        ]))
        elements.append(t)
        elements.append(Spacer(1, 8))
    # 3b
    elements.append(Paragraph("3b. Completed Courses", styles['SubHeading']))
    completed_df = fetch_courses("Completed")
    if not completed_df.empty:
        data = [[Paragraph(h, styles['TableHeader']) for h in ["ID", "Name", "Semester", "Grade"]]] + [
            [Paragraph(safe_text(str(row["course_id"])), styles['TableCell']),
             Paragraph(safe_text(str(row["course_name"])), styles['TableCell']),
             Paragraph(safe_text(str(row["semester"])), styles['TableCell']),
             Paragraph(safe_text(str(row["grade"])), styles['TableCell'])] for _, row in completed_df.iterrows()
        ]
        t = Table(data, colWidths=[25*mm, 70*mm, 30*mm, 20*mm])
        t.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('BACKGROUND', (0,0), (-1,0), colors.whitesmoke)
        ]))
        elements.append(t)
        elements.append(Spacer(1, 8))
    # 3c
    elements.append(Paragraph("3c. Leftover Courses", styles['SubHeading']))
    leftover_df = fetch_courses("Leftover")
    if not leftover_df.empty:
        data = [[Paragraph(h, styles['TableHeader']) for h in ["ID", "Name", "Semester"]]] + [
            [Paragraph(safe_text(str(row["course_id"])), styles['TableCell']),
             Paragraph(safe_text(str(row["course_name"])), styles['TableCell']),
             Paragraph(safe_text(str(row["semester"])), styles['TableCell'])] for _, row in leftover_df.iterrows()
        ]
        t = Table(data, colWidths=[30*mm, 80*mm, 50*mm])
        t.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('BACKGROUND', (0,0), (-1,0), colors.whitesmoke)
        ]))
        elements.append(t)
        elements.append(Spacer(1, 8))

    # 4. Absence Summary
    elements.append(Paragraph("4. Absence Summary", styles['Heading']))
    absence_query = text("""
        SELECT e.course_id, c.course_name, e.semester,
               COALESCE(a.absence_count, 0) AS absences,
               c.absence_limit
        FROM Student_Course_Enrollment e
        JOIN Course c ON c.course_id = e.course_id
        LEFT JOIN Student_Course_Absence a 
            ON e.student_id = a.student_id AND e.course_id = a.course_id AND e.semester = a.semester
        WHERE e.status = 'Current' AND e.student_id = :student_id
    """)
    absence_df = pd.read_sql(absence_query, engine, params={"student_id": student_id})
    absence_df["Status"] = absence_df.apply(lambda row: "Exceeded" if row["absences"] >= row["absence_limit"] else "OK", axis=1)
    if not absence_df.empty:
        data = [[Paragraph(h, styles['TableHeader']) for h in ["ID", "Name", "Semester", "Absences", "Limit", "Status"]]] + [
            [Paragraph(safe_text(str(row["course_id"])), styles['TableCell']),
             Paragraph(safe_text(str(row["course_name"])), styles['TableCell']),
             Paragraph(safe_text(str(row["semester"])), styles['TableCell']),
             Paragraph(safe_text(str(row["absences"])), styles['TableCell']),
             Paragraph(safe_text(str(row["absence_limit"])), styles['TableCell']),
             Paragraph(safe_text(str(row["Status"])), styles['TableCell'])] for _, row in absence_df.iterrows()
        ]
        t = Table(data, colWidths=[25*mm, 60*mm, 30*mm, 20*mm, 20*mm, 20*mm])
        t.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('BACKGROUND', (0,0), (-1,0), colors.whitesmoke)
        ]))
        elements.append(t)
        elements.append(Spacer(1, 8))

    # 5. High Risk
    risk_check = pd.read_sql(text("SELECT 1 FROM High_Risk_Student WHERE student_id = :student_id"), engine, params={"student_id": student_id})
    if not risk_check.empty:
        elements.append(Paragraph('<font color="red"><b>⚠️ This student is classified as high risk due to a cumulative GPA below 2.0. Immediate academic advising is recommended.</b></font>', styles['Body']))
        elements.append(Spacer(1, 8))

    # 6. Advisor Suggestions (auto-suggestions)
    elements.append(Paragraph("6. Advisor Suggestions", styles['Heading']))
    suggestions_query = text("""
        SELECT c.course_id, c.course_name, c.difficulty_rating,
               COALESCE(a.absence_count, 0) AS absences, c.absence_limit,
               e.grade
        FROM Student_Course_Enrollment e
        JOIN Course c ON c.course_id = e.course_id
        LEFT JOIN Student_Course_Absence a ON a.course_id = c.course_id AND a.student_id = e.student_id
        WHERE e.student_id = :student_id AND e.status = 'Current'
    """)
    suggestions = pd.read_sql(suggestions_query, engine, params={"student_id": student_id})

    # Fetch completed courses with grades and difficulty
    completed_courses_query = text("""
        SELECT c.course_id, c.course_name, c.difficulty_rating, e.grade
        FROM Student_Course_Enrollment e
        JOIN Course c ON c.course_id = e.course_id
        WHERE e.student_id = :student_id AND e.status = 'Completed'
    """)
    completed_courses = pd.read_sql(completed_courses_query, engine, params={"student_id": student_id})

    bullet_points = []
    # GPA-based suggestion
    if student['current_gpa'] < 2.0:
        bullet_points.append('<b>GPA Warning:</b> Current GPA (' + str(student['current_gpa']) + ') is below 2.0. Consider retaking courses with low grades.')
    # Course-specific suggestions
    for _, row in suggestions.iterrows():
        if row["difficulty_rating"] and row["difficulty_rating"] >= 3:
            bullet_points.append(f'<b>High Difficulty:</b> Monitor {row["course_id"]} ({row["course_name"]})')
        if row["absence_limit"] and row["absences"] >= row["absence_limit"] * 0.75:
            bullet_points.append(f'<b>Absence Warning:</b> Absences in {row["course_id"]} nearing limit ({row["absences"]}/{row["absence_limit"]})')
        grade = row["grade"]
        try:
            if grade and float(grade) < 60:
                bullet_points.append(f'<b>Low Grade:</b> Low grade in {row["course_id"]} ({row["course_name"]}). Consider seeking additional help or tutoring.')
        except (ValueError, TypeError):
            pass  # Skip non-numeric grades
        # --- New: Potential Risk Based on Past Performance ---
        risk_grades = ["C+", "C", "D+", "D", "F", "W", "DN"]
        for _, comp in completed_courses.iterrows():
            if (
                comp["difficulty_rating"] == row["difficulty_rating"]
                and str(comp["grade"]).strip().upper() in risk_grades
            ):
                bullet_points.append(f'<b>Potential Risk Based on Past Performance:</b> {row["course_id"]} ({row["course_name"]}) has a difficulty similar to a previous course ({comp["course_id"]}) where you scored {comp["grade"]}.')
                break
    if bullet_points:
        elements.append(ListFlowable([
            ListItem(Paragraph(safe_text(bp), styles['Body'])) for bp in bullet_points
        ], bulletType='bullet', leftIndent=20))
    else:
        elements.append(Paragraph("No suggestions at this time.", styles['Body']))
    elements.append(Spacer(1, 8))

    # 7. Notes Section
    elements.append(Paragraph("7. Advisor Notes", styles['Heading']))
    elements.append(Paragraph("[__________________________]", styles['Body']))
    elements.append(Paragraph("(Advisor can add manual comments here)", styles['Body']))

    doc.build(elements)
    print(f"✅ PDF saved to {output_path} (ReportLab version)")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python3 generate_report.py <student_id>")
        sys.exit(1)
    try:
        student_id = int(sys.argv[1])
        print(f"Running generate_student_report_reportlab for student_id={student_id}...")
        generate_student_report_reportlab(student_id=student_id)
    except ValueError:
        print("Error: student_id must be an integer")
        sys.exit(1)
    except Exception as e:
        print(f"Error generating report: {str(e)}")
        sys.exit(1) 