const { DataTypes } = require('sequelize');
const sequelize = require('../config/database');
const Student = require('./Student');
const Course = require('./Course');

const CourseRating = sequelize.define('CourseRating', {
  rating_id: {
    type: DataTypes.INTEGER,
    primaryKey: true,
    autoIncrement: true
  },
  student_id: {
    type: DataTypes.INTEGER,
    allowNull: false,
    references: { model: Student, key: 'student_id' }
  },
  course_id: {
    type: DataTypes.STRING,
    allowNull: false,
    references: { model: Course, key: 'course_id' }
  },
  rating: {
    type: DataTypes.INTEGER, // or FLOAT if you prefer decimals
    allowNull: false,
    validate: { min: 1, max: 5 } // 1-5 stars
  },
  feedback: {
    type: DataTypes.TEXT,
    allowNull: true, // Making it optional but recommended
    comment: 'Student feedback about their course experience'
  }
}, {
  timestamps: true, // Keeps createdAt and updatedAt
  indexes: [
    // Adding an index for faster lookup when showing a student's ratings
    {
      name: 'idx_student_course',
      fields: ['student_id', 'course_id'],
      unique: true // Ensures one rating per student per course
    }
  ]
});

// Associations
Student.hasMany(CourseRating, { foreignKey: 'student_id' });
CourseRating.belongsTo(Student, { foreignKey: 'student_id' });

Course.hasMany(CourseRating, { foreignKey: 'course_id' });
CourseRating.belongsTo(Course, { foreignKey: 'course_id' });

module.exports = CourseRating;