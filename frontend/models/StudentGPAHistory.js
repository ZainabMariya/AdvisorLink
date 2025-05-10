const { DataTypes } = require('sequelize');
const sequelize = require('../config/database');
const Student = require('./Student');

const StudentGPAHistory = sequelize.define('Student_GPA_History', {
  student_id: {
    type: DataTypes.INTEGER,
    allowNull: false,
    primaryKey: true
  },
  semester: {
    type: DataTypes.STRING(20),
    allowNull: false,
    primaryKey: true
  },
  gpa: {
    type: DataTypes.FLOAT,
    allowNull: false,
    validate: { min: 0.0, max: 4.0 }
  }
}, {
  tableName: 'Student_GPA_History',
  timestamps: false
});

StudentGPAHistory.belongsTo(Student, {
  foreignKey: 'student_id',
  onDelete: 'CASCADE'
});
Student.hasMany(StudentGPAHistory, { foreignKey: 'student_id' });

module.exports = StudentGPAHistory;
