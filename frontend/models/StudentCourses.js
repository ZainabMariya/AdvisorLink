const Student = require('../models/Student');
const Course = require('../models/Course');
const StudentCourseEnrollment = require('../models/StudentCourseEnrollment');

const studentDetails = async (req, res) => {
  try {
    const studentId = req.params.id;

    // Get student basic info
    const student = await Student.findByPk(studentId);
    
    if (!student) {
      return res.status(404).send('Student not found');
    }

    // Get course enrollments with course details
    const enrollments = await StudentCourseEnrollment.findAll({
      where: { student_id: studentId },
      include: [{
        model: Course,
        attributes: ['course_id', 'course_name', 'credit_hours', 'course_desc']
      }]
    });

    // Prepare student data with courses properly categorized
    const studentData = {
      ...student.toJSON(),
      courses: enrollments.map(enrollment => enrollment.toJSON())
    };

    res.render('Student', { user: studentData });
  } catch (error) {
    console.error('Error fetching student details:', error);
    res.status(500).send('Server error');
  }
};

module.exports = {
  studentDetails
};