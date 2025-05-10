const { DataTypes } = require('sequelize');
const sequelize = require('../config/database');
const Student = require('./Student');
const Course = require('./Course');
const StudentCourseAbsences = require('./StudentCourseAbsences');

const StudentCourseEnrollment = sequelize.define('Student_Course_Enrollment', {
  student_id: {
    type: DataTypes.INTEGER,
    primaryKey: true,
    references: {
      model: Student,
      key: 'student_id'
    },
    onDelete: 'CASCADE'
  },
  course_id: {
    type: DataTypes.STRING(10),
    primaryKey: true,
    references: {
      model: Course,
      key: 'course_id'
    },
    onDelete: 'CASCADE'
  },
  semester: {
    type: DataTypes.STRING(20),
    allowNull: false
  },
  status: {
    type: DataTypes.ENUM('Completed', 'Current', 'Leftover'),
    allowNull: false
  },
  grade: {
    type: DataTypes.STRING(2),
    allowNull: true,
    validate: {
      isIn: [['A+', 'A', 'B+', 'B', 'C+', 'C', 'D+', 'D', 'F', 'W', 'DN', null]]
    }
  }
}, {
  tableName: 'Student_Course_Enrollment',
  timestamps: false
});

// Associations
StudentCourseEnrollment.belongsTo(Student, {
  foreignKey: 'student_id',
  onDelete: 'CASCADE',
  constraints: false
});

StudentCourseEnrollment.belongsTo(Course, {
  foreignKey: 'course_id',
  onDelete: 'CASCADE',
  constraints: false

});


StudentCourseEnrollment.hasOne(StudentCourseAbsences, {
  foreignKey: 'course_id',
  sourceKey: 'course_id',
  constraints: false
});

StudentCourseAbsences.belongsTo(StudentCourseEnrollment, {
  foreignKey: 'course_id',
  targetKey: 'course_id',
  constraints: false
});

module.exports = StudentCourseEnrollment;
